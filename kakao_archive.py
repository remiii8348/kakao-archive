import streamlit as st
import pandas as pd
import re
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 구글 API 인증 (스트림릿 클라우드 시크릿 활용) ---
def get_drive_service():
    # 스트림릿 클라우드 웹사이트의 Settings > Secrets에 입력한 값을 가져옵니다.
    creds_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(creds_info)
    return build('drive', 'v3', credentials=creds)

# 전역 서비스 객체 생성
service = get_drive_service()
FOLDER_ID = "1TJbWF3x_pj2htu77bbf4WhlfX390cYxe"

# --- 2. 데이터 가져오기 (캐싱 적용) ---
@st.cache_data(ttl=600) # 10분마다 갱신
def fetch_data():
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents", 
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    
    txt_file = next((f for f in files if f['name'] == 'kakao.txt'), None)
    if not txt_file:
        return None, None
    
    request = service.files().get_media(fileId=txt_file['id'])
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    
    return fh.getvalue().decode('utf-8'), files

# --- 3. 파싱 함수 ---
def parse_kakao(text):
    date_pattern = re.compile(r'^-+ (\d{4}년 \d{1,2}월 \d{1,2}일 .요일) -+$')
    msg_pattern = re.compile(r'^\[(.+?)\] \[(.+?)\] (.+)$')
    
    data = []
    current_date = None
    for line in text.split('\n'):
        line = line.strip()
        d_match = date_pattern.match(line)
        if d_match:
            current_date = d_match.group(1)
            continue
        m_match = msg_pattern.match(line)
        if m_match and current_date:
            content = m_match.group(3)
            img_name = None
            if "파일: " in content:
                img_name = content.replace("파일: ", "").strip()
                if not img_name.lower().endswith(('.jpg', '.png', '.jpeg', '.gif')):
                    img_name = None

            data.append({
                'date': current_date, 'user': m_match.group(1),
                'time': m_match.group(2), 'message': content, 'img_name': img_name
            })
    return pd.DataFrame(data)

# --- 4. 메인 화면 구성 ---
st.set_page_config(page_title="카톡 아카이브", layout="centered")
st.title("💬 My Kakao Archive")

try:
    raw_text, file_list = fetch_data()
    if raw_text:
        df = parse_kakao(raw_text)
        all_dates = df['date'].unique().tolist()
        selected_date = st.sidebar.selectbox("📅 날짜 선택", all_dates[::-1])
        
        st.subheader(f"📅 {selected_date}")
        day_df = df[df['date'] == selected_date]

        for _, row in day_df.iterrows():
            with st.chat_message("user"):
                st.caption(f"{row['user']} | {row['time']}")
                if row['img_name']:
                    img_file = next((f for f in file_list if f['name'] == row['img_name']), None)
                    if img_file:
                        st.image(f"https://drive.google.com/uc?id={img_file['id']}")
                    else:
                        st.info(f"🖼 사진 없음: {row['img_name']}")
                else:
                    st.write(row['message'])
except Exception as e:
    st.error(f"연동 오류: {e}")
