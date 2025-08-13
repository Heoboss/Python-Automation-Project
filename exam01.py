# request  : client -> server
# response : server -> client

# python server
# 1) flask : 마이크로 웹 프레임워크
# 2) Django : 모든 기능이 포함!! (flask보다 10~20배 무겁다)

from flask import Flask           # route 경로 ,run 서버실행 # 클래스
from flask import render_template # html load # 함수
from flask import request         # 사용자가 보낸 정보 # 함수
from flask import redirect        # 페이지 이동 # 함수
from flask import make_response   # 페이지 이동 시 정보 유지!! # 함수

from aws import detect_labels_local_file, compare_faces_aws

# 파일 이름 보안 처리 라이브러리
from werkzeug.utils import secure_filename

import os
# static 폴더가 없다면 만들어라
if not os.path.exists("static"):
    os.mkdir("static")

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/compare", methods=["POST"])
def compare_faces():
    
    if request.method == "POST":
        file1 = request.files["file1"]
        file2 = request.files["file2"]
        
        # file을 static 폴더에 저장하고
        file1_name = secure_filename(file1.filename)
        file1.save("static/" + file1_name)
        file2_name = secure_filename(file2.filename)
        file2.save("static/" + file2_name)
        
        r = compare_faces_aws(("static/" + file1_name), ("static/" + file2_name))
    
    return r

@app.route("/detect", methods=["POST"])
def detect_label():
    # flask에서 보안 규칙상
    # file이름을 secure처리 해야한다
    if request.method=="POST":
        file = request.files["file"]
        
        # file을 static 폴더에 저장하고
        file_name = secure_filename(file.filename)
        file.save("static/" + file_name)
        # 해당 경로를 detect_labels~ 함수에 전달!!
        r = detect_labels_local_file("static/" + file_name)
    return r


@app.route("/secret", methods=["POST"])
def box():
    try:
        if request.method == "POST":
            # get - > args[key], post -> form[key]
            hidden = request.form["hidden"]
            return f"비밀 정보 : {hidden}"
    except:
        return "데이터 전송 실패!"
    
@app.route("/login", methods=["GET"])
def login():
    if request.method == "GET":
        # 페이지 이동 : redirect 방식
        # 페이지가 이동하더라도
        # 정보를 남겨 사용!!
        login_id = request.args["login_id"]
        login_pw = request.args["login_pw"]
        if login_id == "pas901" and login_pw == "4321":
            # 로그인 성공
            response = redirect("/login/success")
            # response에 정보를 담을 수 있는 순간 확보
            response.set_cookie("user", login_id)
            return response
        else:
            # 로그인 실패
            return redirect("/")

@app.route("/login/success", methods=["GET"])

def login_success():
    login_id = request.cookies.get("user")
    return f"{login_id}님 환영합니다."
    
if __name__ == "__main__":
    app.run(host="0.0.0.0")

