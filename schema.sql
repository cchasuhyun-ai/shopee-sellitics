-- Shopee Sellitics : Supabase DB 스키마
-- ============================================================
-- Supabase 프로젝트 생성 후, 왼쪽 메뉴의 "SQL Editor"에 이 파일 내용을
-- 전체 복사해서 붙여넣고 "Run"을 누르면 아래 테이블/트리거/RLS 정책이 만들어집니다.
--
-- 설계 메모
-- ------------------------------------------------------------
-- - 로그인은 Supabase Auth(이메일+비밀번호)를 사용합니다. 클라이언트가 회원가입하면
--   auth.users에 행이 생기고, 트리거(handle_new_user)가 profiles에 회사명을 복사합니다.
-- - vat_filings.user_id로 auth.users를 참조해서 "누구의 신고 건"인지 구분하고,
--   RLS(Row Level Security)로 본인(auth.uid()) 소유 행만 조회/수정 가능하도록 제한합니다.
-- - 각 탭(소포수령증 업로드/그 밖의 매출/카드사용내역/매입세액)에서 표로 다루는
--   데이터는 열 구성이 유동적이라 jsonb(레코드 배열)로 저장하고, 합계처럼
--   다른 화면에서 다시 계산에 쓰는 값만 별도 숫자 컬럼으로 둡니다.

create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
-- 마이그레이션: 로그인 도입 이전(거래처명 텍스트 기반) 스키마가 이미 있는 경우 정리
-- ------------------------------------------------------------
-- 거래처명 텍스트로만 구분하던 테스트 데이터는 실제 회원 계정과 연결할 수 없으므로 정리하고,
-- user_id 기준 제약으로 교체합니다. vat_filings 테이블이 아직 없으면(=신규 설치) 아무 것도 하지 않습니다.
do $$
begin
    if to_regclass('public.vat_filings') is not null then
        delete from vat_filings where user_id is null;

        alter table vat_filings drop constraint if exists vat_filings_client_name_period_year_period_half_key;
        alter table vat_filings drop constraint if exists vat_filings_user_id_fkey;
        alter table vat_filings add constraint vat_filings_user_id_fkey
            foreign key (user_id) references auth.users(id) on delete cascade;
        alter table vat_filings alter column user_id set not null;

        alter table vat_filings drop constraint if exists vat_filings_user_id_period_year_period_half_key;
        alter table vat_filings add constraint vat_filings_user_id_period_year_period_half_key
            unique (user_id, period_year, period_half);
    end if;
end $$;

-- ------------------------------------------------------------
-- 회원 프로필 (회사명 등 부가 정보)
-- ------------------------------------------------------------
create table if not exists profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    company_name text not null,
    created_at timestamptz not null default now()
);

alter table profiles enable row level security;

drop policy if exists "select own profile" on profiles;
create policy "select own profile" on profiles
    for select using (auth.uid() = id);

drop policy if exists "update own profile" on profiles;
create policy "update own profile" on profiles
    for update using (auth.uid() = id);

-- 회원가입(auth.users insert) 시 회원가입 폼에서 넘긴 company_name 메타데이터를
-- profiles에 자동으로 복사하는 트리거. security definer로 RLS를 우회해서 insert합니다.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
    insert into public.profiles (id, company_name)
    values (new.id, coalesce(new.raw_user_meta_data ->> 'company_name', new.email));
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ------------------------------------------------------------
-- 거래처(회원) + 신고기간 단위의 "신고 건" (부모 레코드)
-- ------------------------------------------------------------
create table if not exists vat_filings (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    client_name text not null, -- 표시용(회원가입 시 입력한 회사명을 복사해서 저장)
    period_year int not null,
    period_half text not null check (period_half in ('상반기', '하반기')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, period_year, period_half)
);

-- [매출] 소포수령증 업로드 확정 결과
create table if not exists sales_uploads (
    filing_id uuid primary key references vat_filings(id) on delete cascade,
    confirmed_rows jsonb not null default '[]'::jsonb, -- 확정된 취합표(구매자/금액/환율 등 포함)
    raw_rows jsonb not null default '[]'::jsonb,        -- OCR/PDF 파싱 원본 텍스트
    sheet_data jsonb not null default '{}'::jsonb,      -- 엑셀 다운로드용 파일별 원본 표
    updated_at timestamptz not null default now()
);

-- [매출] 그 밖의 매출 입력 확정 결과
create table if not exists other_sales (
    filing_id uuid primary key references vat_filings(id) on delete cascade,
    summary jsonb not null default '[]'::jsonb,        -- 항목별(세금계산서/카드·현금영수증/기타) 공급가액·세액
    supply_total numeric not null default 0,
    tax_total numeric not null default 0,
    evidence_files jsonb not null default '[]'::jsonb, -- 증빙 파일 메타데이터([{name,size}]), 파일 실물은 저장하지 않음
    updated_at timestamptz not null default now()
);

-- [매입] 카드사용내역 입력 확정 결과
create table if not exists card_usage (
    filing_id uuid primary key references vat_filings(id) on delete cascade,
    rows jsonb not null default '[]'::jsonb, -- 거래일자/가맹점명/사업자등록번호/구분/공급가액/세액/비고/출처
    general_supply_total numeric not null default 0,
    general_tax_total numeric not null default 0,
    fixed_asset_supply_total numeric not null default 0,
    fixed_asset_tax_total numeric not null default 0,
    updated_at timestamptz not null default now()
);

-- [매입] 매입세액 입력 확정 결과
create table if not exists purchase_tax (
    filing_id uuid primary key references vat_filings(id) on delete cascade,
    summary jsonb not null default '[]'::jsonb, -- 항목별 공급가액·세액 + 합계/차감계 행
    net_tax_total numeric not null default 0,
    updated_at timestamptz not null default now()
);

create index if not exists idx_vat_filings_lookup
    on vat_filings (user_id, period_year, period_half);

-- ------------------------------------------------------------
-- RLS: 로그인한 본인 소유 데이터만 조회/수정/삭제 가능
-- ------------------------------------------------------------
alter table vat_filings enable row level security;
alter table sales_uploads enable row level security;
alter table other_sales enable row level security;
alter table card_usage enable row level security;
alter table purchase_tax enable row level security;

drop policy if exists "own filings" on vat_filings;
create policy "own filings" on vat_filings
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- 자식 테이블은 filing_id로 vat_filings를 조인해서 소유자를 확인합니다.
drop policy if exists "own sales_uploads" on sales_uploads;
create policy "own sales_uploads" on sales_uploads
    for all
    using (exists (select 1 from vat_filings f where f.id = sales_uploads.filing_id and f.user_id = auth.uid()))
    with check (exists (select 1 from vat_filings f where f.id = sales_uploads.filing_id and f.user_id = auth.uid()));

drop policy if exists "own other_sales" on other_sales;
create policy "own other_sales" on other_sales
    for all
    using (exists (select 1 from vat_filings f where f.id = other_sales.filing_id and f.user_id = auth.uid()))
    with check (exists (select 1 from vat_filings f where f.id = other_sales.filing_id and f.user_id = auth.uid()));

drop policy if exists "own card_usage" on card_usage;
create policy "own card_usage" on card_usage
    for all
    using (exists (select 1 from vat_filings f where f.id = card_usage.filing_id and f.user_id = auth.uid()))
    with check (exists (select 1 from vat_filings f where f.id = card_usage.filing_id and f.user_id = auth.uid()));

drop policy if exists "own purchase_tax" on purchase_tax;
create policy "own purchase_tax" on purchase_tax
    for all
    using (exists (select 1 from vat_filings f where f.id = purchase_tax.filing_id and f.user_id = auth.uid()))
    with check (exists (select 1 from vat_filings f where f.id = purchase_tax.filing_id and f.user_id = auth.uid()));
