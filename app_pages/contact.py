"""
문의하기 (문의)
================
사용자가 담당 세무사에게 문의사항과 증빙·검토자료(PDF, 엑셀 등)를 이메일로 보낼 수 있는
페이지입니다. 받는 사람의 이메일 주소는 화면에 노출하지 않고, 서버(Streamlit) 쪽에서
SMTP를 통해 발송합니다. SMTP 계정 정보(호스트/포트/계정/비밀번호)는
.streamlit/secrets.toml(깃에는 올라가지 않음)에서 읽어옵니다.
"""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import streamlit as st

CATEGORY_OPTIONS = ["일반 문의", "자료 검토 요청", "오류/버그 신고", "기타"]
ALLOWED_ATTACHMENT_TYPES = ["pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg"]
MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20MB


def _sanitize_header(value: str) -> str:
    """이메일 헤더 인젝션 방지를 위해 개행 문자를 제거합니다."""
    return value.replace("\r", " ").replace("\n", " ").strip()


def _get_mail_credentials():
    try:
        email_secrets = st.secrets["email"]
        smtp_user = email_secrets["smtp_user"]
        smtp_password = email_secrets["smtp_password"]
        smtp_host = email_secrets.get("smtp_host", "smtp.naver.com")
        smtp_port = int(email_secrets.get("smtp_port", 587))
    except Exception:
        return None, None, None, None
    if not smtp_user or not smtp_password or smtp_password.startswith("REPLACE_"):
        return None, None, None, None
    return smtp_user, smtp_password, smtp_host, smtp_port


def send_inquiry_email(
    smtp_host, smtp_port, smtp_user, smtp_password, sender_name, sender_email, category, message, files
):
    """작성한 문의 내용을 첨부파일과 함께 담당자에게 이메일로 발송합니다."""
    safe_name = _sanitize_header(sender_name) or "웹앱 방문자"
    safe_email = _sanitize_header(sender_email)
    safe_category = _sanitize_header(category)

    msg = MIMEMultipart()
    msg["Subject"] = f"[문의하기] {safe_name} - {safe_category}"
    msg["From"] = formataddr((safe_name, smtp_user))
    msg["To"] = smtp_user
    msg["Reply-To"] = safe_email

    body = f"보낸 사람: {safe_name}\n회신 이메일: {safe_email}\n문의 유형: {safe_category}\n\n{message}"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for uploaded_file in files:
        part = MIMEApplication(uploaded_file.getvalue())
        part.add_header("Content-Disposition", "attachment", filename=uploaded_file.name)
        msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [smtp_user], msg.as_string())


st.title("문의하기")
st.caption("문의 · 세무 상담 및 자료 검토 요청")
st.write(
    "이용 중 궁금한 점이나 검토가 필요한 자료가 있다면 아래 양식을 작성해 보내주세요. "
    "담당 세무사에게 바로 전달됩니다. 세금계산서, 영수증 등 증빙이나 검토받고 싶은 파일"
    "(PDF, 엑셀 등)을 함께 첨부할 수 있습니다."
)

smtp_user, smtp_password, smtp_host, smtp_port = _get_mail_credentials()
mail_configured = bool(smtp_user and smtp_password)

if not mail_configured:
    st.warning("현재 이메일 발송 기능이 설정되지 않아 문의를 보낼 수 없습니다. 관리자에게 알려주세요.")

with st.form("contact_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        sender_name = st.text_input("이름 / 상호", key="contact_name")
    with col2:
        sender_email = st.text_input(
            "회신받을 이메일", key="contact_email", placeholder="example@email.com"
        )
    category = st.selectbox("문의 유형", CATEGORY_OPTIONS, key="contact_category")
    message = st.text_area(
        "문의 내용", height=180, key="contact_message", placeholder="문의하실 내용을 자세히 적어주세요."
    )
    attachments = st.file_uploader(
        "첨부파일 (PDF, 엑셀 등 증빙·검토자료, 여러 개 선택 가능)",
        type=ALLOWED_ATTACHMENT_TYPES,
        accept_multiple_files=True,
        key="contact_files",
    )
    submitted = st.form_submit_button("문의 보내기", type="primary", disabled=not mail_configured)

if submitted:
    errors = []
    if not sender_name.strip():
        errors.append("이름/상호를 입력해주세요.")
    if not sender_email.strip() or "@" not in sender_email:
        errors.append("올바른 회신 이메일 주소를 입력해주세요.")
    if not message.strip():
        errors.append("문의 내용을 입력해주세요.")
    total_size = sum(f.size for f in attachments) if attachments else 0
    if total_size > MAX_TOTAL_ATTACHMENT_BYTES:
        errors.append("첨부파일 전체 용량은 20MB를 넘을 수 없습니다.")

    if errors:
        for error in errors:
            st.error(error)
    else:
        try:
            with st.spinner("문의를 전송하는 중입니다..."):
                send_inquiry_email(
                    smtp_host,
                    smtp_port,
                    smtp_user,
                    smtp_password,
                    sender_name,
                    sender_email,
                    category,
                    message,
                    attachments or [],
                )
            st.success("문의가 정상적으로 전송되었습니다. 빠른 시일 내에 회신 드리겠습니다.")
        except Exception:
            st.error("메일 전송 중 오류가 발생했습니다. 잠시 후 다시 시도해주시거나 관리자에게 알려주세요.")

st.caption(
    "※ 입력하신 이름과 이메일은 문의 회신 용도로만 사용되며, 그 외 다른 목적으로 사용되지 않습니다."
)
