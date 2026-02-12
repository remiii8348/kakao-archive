import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import re
import os

# --- 1. 구글 드라이브 인증 (슈퍼 클리너 적용) ---
def get_gdrive_service():
    try:
        # 개별 키 로드
        raw_key = st.secrets["PRIVATE_KEY"]
        
        # 1차 청소: 문자열 형태의 \n이 있으면 실제 줄바꿈으로 변경
        clean_key = raw_key.replace("\\n", "\n")
        
        # 2차 청소: 각 줄 끝의 불필요한 공백 제거 (PEM 로더 에러의 주범)
        clean_key = "\n".join([line.strip() for line in clean_key.strip().split("\n")])
        
        info = {
            "type": st.secrets["TYPE"],
            "project_id": st.secrets["PROJECT_ID"],
            "private_key_id": st.secrets["PRIVATE_KEY_ID"],
            "private_key": clean_key,
            "client_email": st.secrets["CLIENT_EMAIL"],
            "client_id": st.secrets["CLIENT_ID"],
            "auth_uri": st.secrets["AUTH_URI"],
            "token_uri": st.secrets["TOKEN_URI"],
            "auth_provider_x509_cert_url": st.secrets["AUTH_PROVIDER_X509_CERT_URL"],
            "client_x509_cert_url": st.secrets["CLIENT_X509_CERT_URL"],
            "universe_domain": st.secrets["UNIVERSE_DOMAIN"]
        }
        
        creds = service_account.Credentials.from_service_account_info(info)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"구글 인증 실패: {e}")
        st.stop()

# 서비스 초기화
service = get_gdrive_service()
FOLDER_ID = st.secrets["FOLDER_ID"]
DB_FILE_NAME = "kakao_db.csv"

# --- 2. 드라이브 유틸리티 ---
def upload_to_drive(file_path, file_name):
    file_metadata = {'name': file_name, 'parents': [FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype='text/csv', resumable=True)
    query = f"name='{file_name}' and '{FOLDER_ID}' in parents and trashed=false"
    results = service.files().list(q=query).execute().get('files', [])
    if results:
        service.files().update(fileId=results[0]['id'], media_body=media).execute()
    else:
        service.files().create(body=file_metadata, media_body=media).execute()

def download_csv_from_drive():
    query = f"name='{DB_FILE_NAME}' and '{FOLDER_ID}' in parents and trashed=false"
    results = service.files().list(q=query).execute().get('files', [])
    if not results: return None
    request = service.files().get_media(fileId=results[0]['id'])
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_csv(fh)

# --- 3. 로그인 및 대화 파싱 ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.title("🔐 Kakao Archive")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == st.secrets["MY_PASSWORD"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else: st.error("Wrong Password")
        return False
    return True

def parse_kakao(content):
    data = []
    current_date = ""
    for line in content.splitlines():
        if "---------------" in line:
            m = re.search(r"(\d{4}년 \d{1,2}월 \d{1,2}일)", line)
            if m: current_date = m.group(1)
        match = re.match(r"\[(.*?)\] \[(.*?)\] (.*)", line)
        if match and current_date:
            user, time, msg = match.groups()
            data.append({"date": f"{current_date} {time}", "user": user, "msg": msg})
    return pd.DataFrame(data)

# --- 4. 메인 화면 ---
if check_password():
    st.set_page_config(page_title="카톡 아카이브", layout="wide")
    st.title("📱 카톡 데이터 보관소")

    df = download_csv_from_drive()
    if df is None: df = pd.DataFrame(columns=["date", "user", "msg"])

    with st.sidebar:
        st.header("⚙️ 업데이트")
        txt_file = st.file_uploader("카톡 .txt 업로드", type="txt")
        if st.button("드라이브 동기화"):
            if txt_file:
                with st.spinner("처리 중..."):
                    new_df = parse_kakao(txt_file.read().decode("utf-8"))
                    df = pd.concat([df, new_df]).drop_duplicates(subset=["date", "user", "msg"])
                    df.to_csv("temp_db.csv", index=False)
                    upload_to_drive("temp_db.csv", DB_FILE_NAME)
                    st.success("완료!")
                    st.rerun()

    search = st.text_input("🔍 메시지 검색")
    view_df = df.copy()
    if search:
        view_df = view_df[view_df['msg'].str.contains(search, na=False) | view_df['user'].str.contains(search, na=False)]

    if not view_df.empty:
        for _, row in view_df.iloc[::-1].iterrows():
            with st.chat_message(row['user']):
                st.write(f"**{row['user']}** | {row['date']}")
                st.write(row['msg'])
