from google.cloud import storage
from google.oauth2 import service_account
import os
import base64
import json

def upload_to_gcs(bucket_name, source_file_path, destination_blob_name):
    # Base64 でエンコードされたJSONを環境変数から取得
    b64_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")
    if not b64_json:
        raise RuntimeError("環境変数 GOOGLE_SERVICE_ACCOUNT_BASE64 が設定されていません")

    # Base64をデコードしてJSONとして読み込む
    service_account_info = json.loads(base64.b64decode(b64_json).decode("utf-8"))
    
    # 認証情報オブジェクトを作成
    credentials = service_account.Credentials.from_service_account_info(service_account_info)

    # GCSクライアントを作成（認証情報を渡す）
    client = storage.Client(credentials=credentials)

    # バケットとブロブを指定してアップロード
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_path)
    
    print(f"GCSにアップロードしました: gs://{bucket_name}/{destination_blob_name}")
