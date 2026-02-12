import streamlit as st
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials
import re

# --- 1. 보안 로그인 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 Private Archive")
        pwd = st.text_input("비밀번호를 입력하세요", type="password")
        if st.button("로그인"):
            if pwd == st.secrets["APP_PASSWORD"]: # Secrets에 설정한 비번
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        return False
    return True

# --- 2. 구글 드라이브 연결 ---
@st.cache_resource
def get_drive():
    scope = ['https://www.googleapis.com/auth/drive']
    # Secrets에서 서비스 계정 정보 로드
    key_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    gauth = GoogleAuth()
    gauth.credentials = creds
    return GoogleDrive(gauth)

# --- 3. 텍스트 파싱 로직 (카톡 형식 분석) ---
def parse_kakao_text(text_content):
    lines = text_content.split('\n')
    chat_data = []
    current_date = ""
    
    # 날짜 구분선 패턴 (예: --------------- 2026년 2월 12일 목요일 ---------------)
    date_pattern = re.compile(r'-+ (\d{4}년 \d{1,2}월 \d{1,2}일) .?요일 -+')
    # 메시지 패턴 (예: [이름] [오후 3:30] 메시지)
    msg_pattern = re.compile(r'\[(.+?)\] \[(.+? \d{1,2}:\d{2})\] (.+)')

    for line in lines:
        date_match = date_pattern.match(line)
        if date_match:
            current_date = date_match.group(1)
            continue
            
        msg_match = msg_pattern.match(line)
        if msg_match:
            chat_data.append({
                "date": current_date,
                "user": msg_match.group(1),
                "time": msg_match.group(2),
                "msg": msg_match.group(3)
            })
    return chat_data

# --- 4. 메인 화면 ---
if check_password():
    st.set_page_config(page_title="My Kakao Archive", layout="wide")
    drive = get_drive()
    
    st.sidebar.title("📁 아카이브 목록")
    # 구글 드라이브에서 '카카오톡_통합_아카이브' 폴더 찾기 로직 등...
    # (실제 구현 시 폴더 ID를 Secrets에 넣어두면 더 빠릅니다)
    
    st.title("💬 카카오톡 대화방")
    
    # 예시: 텍스트 파일 하나를 읽어와서 화면에 뿌리기
    # 실제로는 드라이브에서 최신 txt 파일을 가져오게 설정합니다.
    sample_text = "[나] [오후 4:00] 오늘 체리 사진입니다.\n[나] [오후 4:01] 사진" # 예시 데이터
    chats = parse_kakao_text(sample_text)

    for chat in chats:
        is_me = chat['user'] == "나" # 본인 이름으로 설정
        with st.chat_message("user" if is_me else "assistant"):
            st.write(f"**{chat['user']}** ({chat['time']})")
            st.write(chat['msg'])
            
            # 사진 매칭 로직: 메시지가 "사진"일 경우 해당 시간대의 이미지를 드라이브에서 검색
            if "사진" in chat['msg']:
                # drive.ListFile 쿼리로 해당 날짜/시간의 이미지를 가져와 표시
                # st.image(image_url)
                pass