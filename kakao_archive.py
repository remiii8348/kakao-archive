import streamlit as st
import pandas as pd
import re
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- 1. 구글 API 인증 설정 (Secrets 활용) ---
def get_drive_service():
    # 스트림릿 클라우드 설정(Secrets)에 저장된 정보를 불러옵니다.
    creds_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(creds_info)
    return build('drive', 'v3', credentials=creds)

service = get_drive_service()
FOLDER_ID = "1TJbWF3x_pj2htu77bbf4WhlfX390cYxe"

# --- 2. 데이터 가져오기 함수 ---
@st.cache_data(show_spinner="구글 드라이브에서 데이터를 가져오는 중...")
def fetch_data():
    # 폴더 내 파일 리스트업
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents", 
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    
    # kakao.txt 찾기
    txt_file = next((f for f in files if f['name'] == 'kakao.txt'), None)
    if not txt_file:
        return None, None
    
    # 텍스트 파일 다운로드
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
            # 사진 전송 여부 확인 (PC버전 텍스트 기준)
            if "파일: " in content:
                img_name = content.replace("파일: ", "").strip()
                if not img_name.lower().endswith(('.jpg', '.png', '.jpeg', '.gif')):
                    img_name = None

            data.append({
                'date': current_date,
                'user': m_match.group(1),
                'time': m_match.group(2),
                'message': content,
                'img_name': img_name
            })
    return pd.DataFrame(data)

# --- 4. 메인 UI ---
st.set_page_config(page_title="카톡 아카이브", layout="centered")
st.title("💬 카카오톡 아카이브")

try:
    raw_text, file_list = fetch_data()

    if raw_text:
        df = parse_kakao(raw_text)
        all_dates = df['date'].unique().tolist()
        
        # 사이드바 날짜 선택 (최신순)
        selected_date = st.sidebar.selectbox("📅 날짜 선택", all_dates[::-1])
        
        st.subheader(f"📅 {selected_date}")
        day_df = df[df['date'] == selected_date]

        for _, row in day_df.iterrows():
            with st.chat_message("user"):
                st.caption(f"{row['user']} | {row['time']}")
                
                if row['img_name']:
                    # 폴더 내 파일들 중 이름이 같은 이미지 찾기
                    img_file = next((f for f in file_list if f['name'] == row['img_name']), None)
                    if img_file:
                        st.image(f"https://drive.google.com/uc?id={img_file['id']}")
                    else:
                        st.info(f"🖼 사진을 찾을 수 없음: {row['img_name']}")
                else:
                    st.write(row['message'])
    else:
        st.warning("폴더에서 kakao.txt 파일을 찾을 수 없습니다.")

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")
