import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import re
import os
import zipfile

# --- 1. 구글 드라이브 연결 및 인증 설정 ---
def get_gdrive_service():
    # Secrets에서 서비스 계정 정보를 딕셔너리로 가져옴
    info = dict(st.secrets["gdrive_service_account"])
    # 핵심 수정: 문자열 내의 \\n을 실제 줄바꿈 문자로 변환하여 인증 에러 방지
    info["private_key"] = info["private_key"].replace("\\n", "\n")
    
    creds = service_account.Credentials.from_service_account_info(info)
    return build('drive', 'v3', credentials=creds)

# 드라이브 서비스 초기화
try:
    service = get_gdrive_service()
    FOLDER_ID = st.secrets["FOLDER_ID"]
    DB_FILE_NAME = "kakao_db.csv"
except Exception as e:
    st.error(f"설정 에러: {e}")
    st.stop()

# --- 2. 드라이브 유틸리티 함수 ---
def upload_to_drive(file_path, file_name, mime_type='text/csv'):
    """파일을 구글 드라이브에 업로드하거나 기존 파일을 업데이트합니다."""
    file_metadata = {'name': file_name, 'parents': [FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    
    # 기존에 같은 이름의 파일이 있는지 확인
    query = f"name='{file_name}' and '{FOLDER_ID}' in parents and trashed=false"
    results = service.files().list(q=query).execute().get('files', [])
    
    if results:
        # 기존 파일 업데이트
        service.files().update(fileId=results[0]['id'], media_body=media).execute()
    else:
        # 새 파일 생성
        service.files().create(body=file_metadata, media_body=media).execute()

def download_csv_from_drive():
    """드라이브에서 DB(CSV) 파일을 다운로드하여 데이터프레임으로 변환합니다."""
    query = f"name='{DB_FILE_NAME}' and '{FOLDER_ID}' in parents and trashed=false"
    results = service.files().list(q=query).execute().get('files', [])
    
    if not results:
        return None
    
    request = service.files().get_media(fileId=results[0]['id'])
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_csv(fh)

# --- 3. 보안 및 데이터 파싱 로직 ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔐 Kakao Archive Login")
        pwd = st.text_input("접속 비밀번호를 입력하세요", type="password")
        if st.button("로그인"):
            if pwd == st.secrets["MY_PASSWORD"]:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        return False
    return True

def parse_kakao(content):
    """카톡 텍스트 데이터를 날짜/이름/메시지로 파싱합니다."""
    data = []
    current_date = ""
    lines = content.splitlines()
    for line in lines:
        if "---------------" in line:
            match = re.search(r"(\d{4}년 \d{1,2}월 \d{1,2}일)", line)
            if match:
                current_date = match.group(1)
            continue
        
        # [이름] [시간] 메시지 형태 파싱
        m = re.match(r"\[(.*?)\] \[(.*?)\] (.*)", line)
        if m and current_date:
            user, time, msg = m.groups()
            data.append({"date": f"{current_date} {time}", "user": user, "msg": msg})
    return pd.DataFrame(data)

# --- 4. 메인 앱 화면 ---
if check_password():
    st.set_page_config(page_title="카톡 통합 보관소", layout="wide")
    st.title("📱 구글 드라이브 통합 카톡 아카이브")

    # 드라이브에서 기존 데이터 로드
    df = download_csv_from_drive()
    if df is None:
        df = pd.DataFrame(columns=["date", "user", "msg"])

    # 사이드바: 업데이트 기능
    with st.sidebar:
        st.header("🔄 데이터 동기화")
        uploaded_txt = st.file_uploader("카톡 .txt 파일 업로드", type="txt")
        
        if st.button("구글 드라이브에 업데이트"):
            if uploaded_txt:
                with st.spinner("데이터 처리 중..."):
                    new_df = parse_kakao(uploaded_txt.read().decode("utf-8"))
                    # 기존 데이터와 병합 후 중복 제거 (날짜, 유저, 메시지가 모두 같은 경우)
                    df = pd.concat([df, new_df]).drop_duplicates(subset=["date", "user", "msg"], keep="first")
                    
                    # 임시 파일로 저장 후 드라이브 업로드
                    df.to_csv("temp_db.csv", index=False)
                    upload_to_drive("temp_db.csv", DB_FILE_NAME)
                    
                    st.success("드라이브 업데이트 완료!")
                    st.rerun()
            else:
                st.warning("먼저 .txt 파일을 선택해주세요.")

    # 메인 섹션: 검색 및 조회
    st.subheader("📝 대화 기록 검색")
    search_query = st.text_input("🔍 이름 또는 메시지 내용으로 검색")
    
    view_df = df.copy()
    if search_query:
        view_df = view_df[view_df['msg'].str.contains(search_query, na=False) | 
                         view_df['user'].str.contains(search_query, na=False)]

    # 최신 메시지부터 출력 (가장 아래에 있는 것이 최신이므로 역순 출력)
    if not view_df.empty:
        for _, row in view_df.iloc[::-1].iterrows():
            with st.chat_message(row['user']):
                st.write(f"**{row['user']}** | {row['date']}")
                st.write(row['msg'])
    else:
        st.info("표시할 데이터가 없습니다. 파일을 먼저 업로드해주세요.")
