# 소포수령증 PDF 취합 웹앱 - 배포 가이드

웹개발을 처음 해보시는 분들을 위해 아주 상세히 설명합니다.
전체 과정은 **약 15~20분**, **비용은 0원**입니다.

## 파일 구성

```
webapp/
 ├── app.py               ← 화면(웹페이지) 코드
 ├── pdf_processor.py     ← PDF 처리 핵심 로직
 ├── requirements.txt     ← 필요한 파이썬 라이브러리 목록
 ├── packages.txt         ← 필요한 시스템 프로그램 목록 (Tesseract, Poppler)
 └── README.md            ← 이 파일
```

---

## 1단계: GitHub 계정 만들기 (이미 있으면 생략)

1. https://github.com 접속 → 오른쪽 위 "Sign up" 클릭
2. 이메일, 비밀번호 입력해서 계정 생성

GitHub는 코드를 저장해두는 온라인 창고입니다. Streamlit이 이 창고에서 코드를 가져다가 실행해줍니다.

## 2단계: GitHub에 새 저장소(repository) 만들기

1. 로그인 후 오른쪽 위 **+** 버튼 → **New repository** 클릭
2. Repository name: `pdf-aggregator` (원하는 이름으로)
3. **Public** 선택 (무료 배포하려면 Public이어야 함)
4. **Create repository** 클릭

## 3단계: 파일 업로드

1. 방금 만든 저장소 페이지에서 **"uploading an existing file"** 링크 클릭
   (또는 저장소 화면의 **Add file → Upload files** 버튼)
2. 이 폴더 안의 5개 파일(`app.py`, `pdf_processor.py`, `requirements.txt`, `packages.txt`, `README.md`)을
   전부 드래그 앤 드롭으로 올리기
3. 아래 **Commit changes** 버튼 클릭

## 4단계: Streamlit Community Cloud로 배포

1. https://share.streamlit.io 접속
2. **GitHub 계정으로 로그인** (Sign in with GitHub)
3. **New app** 버튼 클릭
4. Repository에서 방금 만든 `pdf-aggregator` 선택
5. Main file path에 `app.py` 입력
6. **Deploy** 버튼 클릭

3~5분 정도 기다리면 배포가 완료되고, 아래와 같은 형태의 주소가 생성됩니다:

```
https://your-app-name.streamlit.app
```

이 주소를 다른 사람에게 공유하면, 그 사람도 브라우저에서 바로 PDF를 업로드하고 결과를 받을 수 있습니다.

---

## 코드를 수정하고 싶을 때

1. GitHub 저장소에서 수정하고 싶은 파일 클릭 → 연필 아이콘(Edit) 클릭
2. 수정 후 **Commit changes**
3. Streamlit Cloud가 자동으로 변경사항을 감지해서 앱을 다시 배포합니다 (1~2분 소요)

---

## 향후 로그인 기능 추가 시 참고사항

`app.py`와 `pdf_processor.py` 안에 `TODO(로그인 연동)` 이라고 표시된 부분들이 있습니다.
나중에 로그인 기능을 추가할 때는:

1. **Supabase** (https://supabase.com) 에서 무료 프로젝트 생성
2. `pip install supabase` 로 라이브러리 설치 (requirements.txt에도 추가)
3. Supabase의 Auth 기능으로 로그인 화면 구성
4. 로그인한 사용자의 ID를 가져와서, 처리 결과(`combined_df`, `raw_df`)를
   Supabase Database에 사용자 ID와 함께 저장
5. 사용자가 재접속하면 그 사용자의 이전 결과를 DB에서 불러와 보여주기

이 단계가 되면 다시 도와드릴 수 있으니 편하게 말씀해주세요.
