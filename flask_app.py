from flask import Flask, send_file, request, jsonify
import os

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