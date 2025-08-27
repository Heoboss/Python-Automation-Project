# 💼 취업 All In One Service

Python Flask와 자동화 스크립트를 활용하여 취업 준비의 모든 과정을 한 곳에서 해결할 수 있도록 돕는 웹 애플리케이션 프로젝트입니다.

<img width="614" height="695" alt="image" src="https://github.com/user-attachments/assets/0f5b3bc6-db85-4bf0-8af7-00881227c9a3" />


<br>

## ✨ 주요 기능 (Key Features)

* **통합 채용 공고 검색 및 요약**
  * **동시 스크래핑:** `ThreadPoolExecutor`를 활용한 멀티스레딩으로 **잡플래닛, 잡코리아, 인크루트**의 채용 정보를 동시에 스크래핑하여 사용자 대기 시간을 최소화했습니다.
  * **상세 정보 제공:** 각 공고의 주요 업무, 자격 요건, 우대 사항 등 상세 정보를 제공하여 사용자가 여러 사이트를 방문할 필요가 없도록 했습니다.

* **기업 정보 조회**
  * **API 연동:** 공공 데이터 포탈 API를 연동하여 기업명 검색만으로 **재무 정보**와 **기업 개요**를 시각적인 차트와 함께 제공합니다.

* **인프런 강의 및 최신 뉴스 검색**
  * **Selenium 활용:** 동적 웹 페이지인 **인프런**과 **네이트 뉴스**를 Selenium으로 안정적으로 크롤링하여 키워드 기반의 강의 및 뉴스 검색 기능을 구현했습니다.

* **사용자 맞춤형 UI/UX**
  * **라이트/다크 모드:** CSS 변수와 JavaScript를 사용하여 사용자가 선호하는 테마를 선택하고, 브라우저(`localStorage`)에 저장하여 다음 방문 시에도 유지되도록 했습니다.
  * **반응형 웹 디자인:** **Tailwind CSS**를 활용하여 모바일, 태블릿, 데스크톱 등 모든 기기에서 최적화된 화면을 제공합니다.

* **사용자 인증 시스템**
  * Flask를 기반으로 간단한 로그인, 회원가입, 로그아웃 기능을 구현하여 사용자별 데이터 캐싱을 지원합니다.

<br>

## 🛠️ 사용된 기술 (Tech Stack)

* **Backend:** `Python`, `Flask`
* **Frontend:** `HTML`, `CSS`, `JavaScript`
* **Crawling & Scraping:** `Selenium`, `BeautifulSoup`, `Requests`
* **Concurrency:** `concurrent.futures.ThreadPoolExecutor`
* **Deployment:** `AWS EC2`

<br>

## 🎥 서비스 시연 (Live Demo)

이 서비스의 주요 기능인 **통합 채용 공고 검색**, **기업 정보 조회**, **다크 모드** 전환 과정을 간략한 GIF로 확인해보세요.

* **라이트/다크 모드**
![다크모드 (1)](https://github.com/user-attachments/assets/0da82dbe-9d8c-414f-a4f2-dcab59da3939)
* **로그인/회원가입**
![로그인_cropped](https://github.com/user-attachments/assets/f977832e-2d5c-4952-a354-20cbddf718f9)
* **채용공고 요약 서비스**


<br>


## 🚀 시작하기 (Getting Started)

### 1. 로컬 환경에서 실행하기 (Local Development)

**1. 저장소 복제**
```bash
git clone https://github.com/Heoboss/Python-Automation-Project.git
cd Python-Automation-Project
```

**2. 가상 환경 생성 및 활성화**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

**3. 의존성 설치**
```bash
pip install -r requirements.txt
```
*(주: `requirements.txt` 파일이 없다면 `pip freeze > requirements.txt` 명령어로 생성해주세요.)*

**4. Flask 앱 실행**
```bash
python3 app.py
```
이제 웹 브라우저에서 `http://127.0.0.1:5000`으로 접속하여 서비스를 확인할 수 있습니다.

### 2. 서버 환경에 배포하기 (Server Deployment)

**1. 저장소 복제**
```bash
git clone https://github.com/Heoboss/Python-Automation-Project.git
cd Python-Automation-Project
```
**2. 시스템 기본 패키지 설치**
```bash
sudo apt update
sudo apt install python3-pip -y
```
**3. 의존성 설치**
```bash
pip install -r requirements.txt
```

**4. 크롬 브라우저 및 드라이버 설치**
Selenium이 크롤링에 사용할 크롬 브라우저를 서버에 설치합니다. webdriver-manager가 드라이버를 자동으로 관리해줍니다.
```bash
# 구글 크롬 최신 안정화 버전을 다운로드합니다.
wget [https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb](https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb)

# 다운로드한 패키지를 설치합니다. (-y 플래그로 모든 질문에 'yes'로 자동 응답)
sudo apt install ./google-chrome-stable_current_amd64.deb -y

# 설치에 사용된 파일을 삭제합니다.
rm google-chrome-stable_current_amd64.deb
```

**5. 스왑 파일(Swap File) 생성**
메모리가 작은 서버(예: 1GB RAM)에서 메모리 부족으로 인해 크롤러 작동 중 서버가 멈추는 현상을 방지합니다.
```bash
# 2GB 크기의 스왑 파일을 생성합니다.
sudo fallocate -l 2G /swapfile

# 파일 권한을 설정합니다.
sudo chmod 600 /swapfile

# 이 파일을 스왑 영역으로 지정합니다.
sudo mkswap /swapfile

# 스왑 파일을 시스템에서 활성화합니다.
sudo swapon /swapfile

# 서버가 재부팅되어도 스왑 설정이 유지되도록 /etc/fstab 파일에 등록합니다.
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**6. Flask 앱 실행**
```bash
python3 app.py
```
이제 웹 브라우저에서 `http://퍼블릭Ipv4주소:5000`으로 접속하여 서비스를 확인할 수 있습니다.
<br>

## 💡 향후 개선 계획 (Future Work)

* \[ \] **AI 면접 연습 기능 추가:** 사용자가 웹캠을 통해 AI와 모의 면접을 진행하고 피드백을 받는 기능
* \[ \] **이력서 자동 완성 기능:** 주요 경력과 스킬을 입력하면 AI가 매력적인 자기소개서 초안을 작성해주는 기능
* \[ \] **카카오톡 알림 기능 고도화:** 사용자가 설정한 조건에 맞는 공고를 매일 정해진 시간에 카카오톡으로 받아보는 기능 완성
* \[ \] **데이터베이스 연동:** 사용자별 검색 기록, 저장한 공고 등을 관리하기 위해 `users.json` 대신 `SQLite`나 `PostgreSQL` 같은 데이터베이스 연동
    
