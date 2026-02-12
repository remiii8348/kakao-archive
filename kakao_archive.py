import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import re
import os
import zipfile

# --- 1. 드라이브 연결 설정 ---
FOLDER_ID = st.secrets["FOLDER_ID"]
DB_FILE_NAME = "kakao_db.csv"

def get_gdrive_service():
    info = st.secrets["gdrive_service_account"]
    creds = service_account.Credentials.from_service_account_info(info)
    return build('drive', 'v3', credentials=creds)

service = get_gdrive_service()

# --- 2. 드라이브 유틸리티 함수 ---
def upload_to_drive(file_name, file_content, mime_type='text/csv'):
    file_metadata = {'name': file_name, 'parents': [FOLDER_ID]}
    if isinstance(file_content, str):
        media = MediaFileUpload(file_content, mimetype=mime_type)
    else:
        media = MediaFileUpload(file_content.name, mimetype=mime_type) # 임시
        
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

# --- 3. 로그인 및 파싱 ---
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
    
    # 드라이브에서 데이터 로드
    df = download_csv_from_drive()
    if df is None: df = pd.DataFrame(columns=["date", "user", "msg"])

    with st.sidebar:
        st.header("⚙️ 데이터 업데이트")
        txt_file = st.file_uploader("카톡 .txt 업로드", type="txt")
        if st.button("구글 드라이브와 동기화"):
            if txt_file:
                new_df = parse_kakao(txt_file.read().decode("utf-8"))
                df = pd.concat([df, new_df]).drop_duplicates(subset=["date", "user", "msg"])
                df.to_csv("temp_db.csv", index=False)
                upload_to_drive(DB_FILE_NAME, "temp_db.csv")
                st.success("동기화 완료!")
                st.rerun()

    # 메시지 검색 및 출력
    search = st.text_input("🔍 검색")
    view_df = df.copy()
    if search:
        view_df = view_df[view_df['msg'].str.contains(search, na=False) | view_df['user'].str.contains(search, na=False)]

    for _, row in view_df.iloc[::-1].iterrows():
        with st.chat_message(row['user']):
            st.write(f"**{row['user']}** | {row['date']}")
            st.write(row['msg'])