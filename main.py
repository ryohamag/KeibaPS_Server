import schedule
import time
import threading
from get_race_schedule import job
from get_race_json import get_race_json
from flask import Flask, send_file, request, jsonify
import os
from selenium import webdriver
from datetime import datetime, timedelta

app = Flask(__name__)

@app.route('/get_json', methods=['GET'])
def get_json():
    # リクエストからファイル名を取得
    file_name = request.args.get('file_name')
    
    # スクリプトのディレクトリを取得
    script_dir = os.path.dirname(__file__)
    
    # ファイルパスを設定（相対パス）
    file_path = os.path.join(script_dir, 'racedata', file_name)
    
    # ファイルが存在するか確認
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({"error": "File not found"}), 404

# スケジュール設定
schedule.every().sunday.at("23:15").do(job)
schedule.every().sunday.at("23:00").do(get_race_json)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# スケジューラーを別スレッドで実行
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# Flask アプリケーションを実行
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)