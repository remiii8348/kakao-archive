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
with st.expander("🔑 구글 인증 (여기를 클릭해서 키 파일을 넣으세요)", expanded=True):
    key_file = st.file_uploader("구글 키 파일(.json)을 여기에 드래그하세요", type="json", key="auth_key")

if not key_file:
    st.info("👆 먼저 구글 키 파일(JSON)을 업로드해야 작동합니다.")
    st.stop()

# --- 인증 처리 ---
try:
    # 업로드된 파일을 즉시 읽어서 인증
    key_info = json.load(key_file)
    creds = service_account.Credentials.from_service_account_info(key_info)
    service = build('drive', 'v3', credentials=creds)
    st.success("✅ 인증 성공!")
except Exception as e:
    st.error(f"❌ 인증 파일 오류: {e}")
    st.stop()

# --- [설정] ---
# 본인의 폴더 ID로 교체되어 있습니다.
FOLDER_ID = "1TJbWF3x_pj2htu77bbf4WhlfX390cYxe"
DB_FILE_NAME = "kakao_db.csv"

# --- 유틸리티 함수 (수정됨: 에러 원인 제거) ---
def upload_to_drive(file_content, file_name, mime_type='text/csv'):
    # 1. 내용을 임시 파일로 저장 (가장 안정적인 방법)
    temp_path = f"temp_{file_name}"
    
    # 데이터가 문자열이면 utf-8로 인코딩해서 저장
    mode = "w" if isinstance(file_content, str) else "wb"
    encoding = "utf-8" if isinstance(file_content, str) else None
    
    with open(temp_path, mode, encoding=encoding) as f:
        f.write(file_content)

    # 2. 구글 드라이브 업로드 준비
    file_metadata = {'name': file_name, 'parents': [FOLDER_ID]}
    media = MediaFileUpload(temp_path, mimetype=mime_type, resumable=True)

    # 3. 기존 파일 있는지 확인
    query = f"name='{file_name}' and '{FOLDER_ID}' in parents and trashed=false"
    results = service.files().list(q=query).execute().get('files', [])
    
    # 4. 업데이트 또는 새로 생성
    if results:
        # 기존 파일이 있으면 덮어쓰기 (Update)
        service.files().update(fileId=results[0]['id'], media_body=media).execute()
    else:
        # 없으면 새로 만들기 (Create)
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
    except Exception as e:
        return None

def parse_kakao(content):
    data = []
    current_date = ""
    lines = content.splitlines()
    for line in lines:
        if "---------------" in line:
            m = re.search(r"(\d{4}년 \d{1,2}월 \d{1,2}일)", line)
            if m: current_date = m.group(1)
            continue
        
        match = re.match(r"\[(.*?)\] \[(.*?)\] (.*)", line)
        if match and current_date:
            user, time, msg = match.groups()
            data.append({"date": f"{current_date} {time}", "user": user, "msg": msg})
    return pd.DataFrame(data)

# --- 메인 로직 ---
# 1. 기존 데이터 로드
df = download_csv_from_drive()
if df is None:
    df = pd.DataFrame(columns=["date", "user", "msg"])

# 2. 사이드바 (업로드 기능)
with st.sidebar:
    st.header("⚙️ 데이터 추가")
    txt_file = st.file_uploader("카톡 대화(.txt) 업로드", type="txt")
    
    if st.button("구글 드라이브에 저장"):
        if txt_file:
            with st.spinner("드라이브에 저장 중입니다..."):
                # 파싱
                new_df = parse_kakao(txt_file.read().decode("utf-8"))
                # 병합 및 중복 제거
                df = pd.concat([df, new_df]).drop_duplicates(subset=["date", "user", "msg"])
                
                # CSV 문자열로 변환
                csv_str = df.to_csv(index=False)
                
                # 업로드 실행 (수정된 함수 사용)
                upload_to_drive(csv_str, DB_FILE_NAME)
                
                st.success("저장 완료!")
                st.rerun()

# 3. 데이터 조회 화면
st.divider()
st.subheader(f"총 대화 {len(df)}건")

search = st.text_input("🔍 대화 내용 검색")
view_df = df.copy()

if search:
    view_df = view_df[view_df['msg'].str.contains(search, na=False) | view_df['user'].str.contains(search, na=False)]

# 최신순 출력
if not view_df.empty:
    for _, row in view_df.iloc[::-1].iterrows():
        with st.chat_message(row['user']):
            st.write(f"**{row['user']}** | {row['date']}")
            st.write(row['msg'])
else:
    st.info("표시할 대화가 없습니다. 파일을 업로드해주세요.")
