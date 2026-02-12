import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import re
import os
import json

# --- 1. 구글 드라이브 인증 (절대 경로 강제 지정) ---
def get_gdrive_service():
    try:
        # [수정됨] 무조건 사용자 바탕화면의 파일을 찾도록 경로 고정
        # 파일명이 google_key.json 인지 꼭 확인하세요!
        key_file_path = r"C:\Users\user\Desktop\google_key.json"
        
        if not os.path.exists(key_file_path):
            st.error(f"❌ 파일 없음: {key_file_path}")
            st.write("👉 팁: 바탕화면에 파일 이름이 'google_key.json'이 맞나요? (확장자 확인 필요)")
            st.stop()
            
        creds = service_account.Credentials.from_service_account_file(key_file_path)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"인증 오류: {e}")
        st.stop()

# 서비스 초기화
service = get_gdrive_service()

# --- 2. 설정 ---
FOLDER_ID = "1TJbWF3x_pj2htu77bbf4WhlfX390cYxe"
DB_FILE_NAME = "kakao_db.csv"
MY_PASSWORD = "fnql" 

# --- 3. 드라이브 유틸리티 ---
def upload_to_drive(file_path, file_name, mime_type='text/csv'):
    file_metadata = {'name': file_name, 'parents': [FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    query = f"name='{file_name}' and '{FOLDER_ID}' in parents and trashed=false"
    results = service.files().list(q=query).execute().get('files', [])
    if results:
        service.files().update(fileId=results[0]['id'], media_body=media).execute()
    else:
        service.files().create(body=file_metadata, media_body=media).execute()

def download_csv_from_drive():
    try:
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
    except:
        return None

# --- 4. 로그인 및 파싱 ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.title("🔐 Kakao Archive Login")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == MY_PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else: st.error("비밀번호 오류")
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

# --- 5. 메인 화면 ---
if check_password():
    st.set_page_config(page_title="카톡 아카이브", layout="wide")
    st.title("📱 카톡 데이터 보관소")

    df = download_csv_from_drive()
    if df is None: df = pd.DataFrame(columns=["date", "user", "msg"])

    with st.sidebar:
        st.header("⚙️ 동기화")
        txt_file = st.file_uploader("카톡 .txt 업로드", type="txt")
        if st.button("구글 드라이브 업데이트"):
            if txt_file:
                with st.spinner("업데이트 중..."):
                    new_df = parse_kakao(txt_file.read().decode("utf-8"))
                    df = pd.concat([df, new_df]).drop_duplicates(subset=["date", "user", "msg"])
                    df.to_csv("temp_db.csv", index=False)
                    upload_to_drive("temp_db.csv", DB_FILE_NAME)
                    st.success("완료!")
                    st.rerun()

    search = st.text_input("🔍 검색")
    view_df = df.copy()
    if search:
        view_df = view_df[view_df['msg'].str.contains(search, na=False) | view_df['user'].str.contains(search, na=False)]

    if not view_df.empty:
        for _, row in view_df.iloc[::-1].iterrows():
            with st.chat_message(row['user']):
                st.write(f"**{row['user']}** | {row['date']}")
                st.write(row['msg'])
