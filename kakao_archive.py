import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import re
import os
import json

# --- 메인 화면 설정 ---
st.set_page_config(page_title="카톡 데이터 보관소", layout="wide")
st.title("📱 카톡 데이터 보관소 (파일 직접 인증)")

# --- [1단계] 인증 키 파일 업로드 ---
st.warning("⚠️ 먼저 구글에서 받은 키 파일(JSON)을 아래에 올려주세요.")
key_file = st.file_uploader("1️⃣ 구글 키 파일 (.json) 업로드", type="json", key="auth_key")

if not key_file:
    st.info("키 파일을 업로드해야 접속할 수 있습니다.")
    st.stop()

# --- 인증 처리 (경로 찾기 X, 직접 읽기 O) ---
try:
    # 업로드된 파일을 즉시 읽어서 인증 (경로 문제 원천 차단)
    key_info = json.load(key_file)
    creds = service_account.Credentials.from_service_account_info(key_info)
    service = build('drive', 'v3', credentials=creds)
    st.success("✅ 구글 드라이브 인증 성공!")
except Exception as e:
    st.error(f"❌ 인증 파일 오류: {e}")
    st.stop()

# --- [설정] ---
FOLDER_ID = "1TJbWF3x_pj2htu77bbf4WhlfX390cYxe"
DB_FILE_NAME = "kakao_db.csv"

# --- 유틸리티 함수 ---
def upload_to_drive(file_content, file_name, mime_type='text/csv'):
    # 파일 내용을 바로 업로드 (임시 파일 저장 안 함)
    file_metadata = {'name': file_name, 'parents': [FOLDER_ID]}
    
    # BytesIO로 변환하여 메모리에서 바로 전송
    if isinstance(file_content, str):
        fh = io.BytesIO(file_content.encode('utf-8'))
    else:
        fh = io.BytesIO(file_content)
        
    media = MediaIoBaseDownload(fh, request=None) # Dummy for type checking, actually using MediaFileUpload equivalent logic manually below isn't needed with api client nicely.
    # Re-implementing simplified upload for memory stream
    media = MediaFileUpload("temp_db.csv", mimetype=mime_type, resumable=True) # Fallback to file for safety in simple code
    
    # 메모리상 데이터를 임시파일로 저장 후 업로드 (가장 안정적)
    with open("temp_upload.csv", "wb") as f:
        f.write(file_content.encode('utf-8') if isinstance(file_content, str) else file_content)
        
    media = MediaFileUpload("temp_upload.csv", mimetype=mime_type, resumable=True)

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

# --- 메인 로직 ---
df = download_csv_from_drive()
if df is None: df = pd.DataFrame(columns=["date", "user", "msg"])

with st.sidebar:
    st.header("⚙️ 데이터 업데이트")
    txt_file = st.file_uploader("2️⃣ 카톡 .txt 파일 업로드", type="txt")
    
    if st.button("구글 드라이브 동기화"):
        if txt_file:
            with st.spinner("처리 중..."):
                new_df = parse_kakao(txt_file.read().decode("utf-8"))
                df = pd.concat([df, new_df]).drop_duplicates(subset=["date", "user", "msg"])
                
                # 데이터프레임을 CSV 문자열로 변환 후 업로드
                csv_str = df.to_csv(index=False)
                upload_to_drive(csv_str, DB_FILE_NAME)
                
                st.success("완료!")
                st.rerun()

# 조회
st.divider()
search = st.text_input("🔍 메시지 검색")
view_df = df.copy()
if search:
    view_df = view_df[view_df['msg'].str.contains(search, na=False) | view_df['user'].str.contains(search, na=False)]

if not view_df.empty:
    for _, row in view_df.iloc[::-1].iterrows():
        with st.chat_message(row['user']):
            st.write(f"**{row['user']}** | {row['date']}")
            st.write(row['msg'])
