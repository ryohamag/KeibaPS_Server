# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
# keiba_scraper/pipelines.py

import os
import json
from google.cloud import storage
from datetime import datetime

class GCSPipeline:
    def __init__(self, bucket_name, export_dir):
        self.bucket_name = bucket_name
        self.export_dir = export_dir
        self.data = []

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            bucket_name=crawler.settings.get("GCS_BUCKET"),
            export_dir=crawler.settings.get("GCS_EXPORT_DIR", "raceschedule")
        )

    def process_item(self, item, spider):
        self.data.append(dict(item))  # Itemをdictに変換して保持
        return item

    def close_spider(self, spider):
        now = datetime.now()
        filename = f"{self.export_dir}/{now.year}{now.month:02}.json"
        local_path = os.path.join(self.export_dir, f"{now.year}{now.month:02}.json")

        # 保存ディレクトリ作成
        os.makedirs(self.export_dir, exist_ok=True)

        # JSONファイルとして保存
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

        # GCSにアップロード
        self.upload_to_gcs(self.bucket_name, local_path, filename)
        print(f"GCSにアップロードしました: {filename}")

    def upload_to_gcs(self, bucket_name, source_file_name, destination_blob_name):
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_name)

