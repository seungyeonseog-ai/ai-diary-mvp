"""원본 DB/AI/Redis 없이 배포 초기화·이행·보존·설정 실패를 검사한다."""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "isolated-deployment-unit-test-secret"
os.environ["OPENAI_API_KEY"] = "synthetic-test-not-a-real-key"
import sqlite3
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from deploy.database import prepare
from deploy.preflight import validate
from deploy.snapshot import create as backup_snapshot, restore as restore_snapshot


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "app.db"
        self.url = "sqlite:///" + self.path.as_posix()

    def test_fresh_then_repeat_preserves_diary_photo_and_activation(self):
        self.assertEqual(prepare(self.url)["action"], "initialized-new")
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        db.execute("INSERT INTO users(id,username,email,hashed_password,nickname) VALUES(1,'synthetic','test@example.org','unused','test')")
        db.execute("INSERT INTO diary_reports(diary_id,user_id,content,title,state,version,timestamp) VALUES(1,1,'synthetic diary','title','saved',1,'2026-11-04 12:00:00')")
        db.execute("INSERT INTO diary_photos(id,user_id,diary_id,client_id,media_type,digest,content,created_at) VALUES('photo',1,1,'client','image/png','digest',X'010203','2026-11-04 12:00:00')")
        db.commit()
        before = list(db.iterdump())
        self.assertEqual(prepare(self.url)["action"], "verified-existing")
        self.assertEqual(list(db.iterdump()), before)

    def test_existing_legacy_is_refused_by_init_and_migrate_backs_up(self):
        prepare(self.url)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TABLE account_plan_choices")
            db.execute("INSERT INTO users(id,username,email,hashed_password,nickname,registered_at) VALUES(1,'synthetic','a@example.org','unused','test','2026-11-04 12:00:00')")
        with self.assertRaises(RuntimeError): prepare(self.url)
        result = prepare(self.url, migrate=True)
        self.assertTrue(result["backup_created"])
        backups = list(self.path.parent.glob("*.pre-migration-*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='account_plan_choices'").fetchone()[0], 0)
        self.assertEqual(prepare(self.url)["action"], "verified-existing")

    def test_unknown_database_is_not_replaced(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE unrelated(value TEXT)")
            db.execute("INSERT INTO unrelated VALUES('preserve')")
        for migrate in (False, True):
            with self.assertRaises(RuntimeError): prepare(self.url, migrate=migrate)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT value FROM unrelated").fetchone()[0], "preserve")

    def test_non_sqlite_and_memory_refused(self):
        for url in ("sqlite:///:memory:", "postgresql://test/test"):
            with self.assertRaises(ValueError): prepare(url)

    def test_concurrent_wrappers_construct_one_model_without_changing_embedding_options(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from app.clients import huggingface_client as module
        module._load_model.cache_clear()
        self.addCleanup(module._load_model.cache_clear)
        with patch.object(module,'HuggingFaceEmbeddings') as constructor:
            with ThreadPoolExecutor(max_workers=8) as pool:
                clients=list(pool.map(lambda _:module.HuggingFaceClient(),range(16)))
            constructor.assert_called_once()
            self.assertTrue(all(client.emb is clients[0].emb for client in clients))
            self.assertEqual(constructor.call_args.kwargs['model_kwargs'],{'device':'cpu','trust_remote_code':False})
            self.assertEqual(constructor.call_args.kwargs['encode_kwargs'],{'normalize_embeddings':True})

    def test_sparse_index_is_shared_by_independent_processes_and_scoped_by_user(self):
        import subprocess,sys,json
        env={**os.environ,"PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8",
             "SPARSE_DB_PATH":str(Path(self.temp.name)/"shared-fts.db")}
        writer="from app.services.sparse_service import SparseIndexService; s=SparseIndexService(); s.upsert_document('산책기록 합성검증', {'doc_id':'test-doc','user_id':1,'session_id':'test-session','type':'summary'}); s.conn.close()"
        reader="import json; from app.services.sparse_service import SparseIndexService; s=SparseIndexService(); print(json.dumps([len(s.search('산책기록',user_id=1)),len(s.search('산책기록',user_id=2))])); s.conn.close()"
        subprocess.run([sys.executable,'-B','-c',writer],env=env,check=True,capture_output=True)
        result=subprocess.run([sys.executable,'-B','-c',reader],env=env,check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(result.stdout),[1,0])

    def test_snapshot_roundtrip_and_nonempty_restore_refusal(self):
        source=Path(self.temp.name)/"source"
        for part in ("app","chroma","redis","beat"):(source/part).mkdir(parents=True)
        prepare("sqlite:///"+(source/"app/app.db").as_posix())
        (source/"chroma/index.bin").write_bytes(b"synthetic-index")
        (source/"redis/appendonly.aof").write_bytes(b"synthetic-queue")
        (source/"beat/celerybeat-schedule").write_bytes(b"synthetic-schedule")
        archive=Path(self.temp.name)/"backup.tar.gz"
        backup_snapshot(source,archive)
        target=Path(self.temp.name)/"target"
        result=restore_snapshot(target,archive)
        self.assertTrue(result["restored"])
        for path in source.rglob("*"):
            if path.is_file():self.assertEqual(path.read_bytes(),(target/path.relative_to(source)).read_bytes())
        self.assertEqual(prepare("sqlite:///"+(target/"app/app.db").as_posix())["action"],"verified-existing")
        with self.assertRaises(RuntimeError):restore_snapshot(target,archive)

    def test_snapshot_rejects_modified_manifest_and_path_traversal(self):
        import tarfile,io,json
        for name in ("app/app.db","../escape"):
            archive=Path(self.temp.name)/("bad-"+str(len(name))+".tar.gz")
            with tarfile.open(archive,"w:gz") as tar:
                data=b"tampered"
                item=tarfile.TarInfo(name);item.size=len(data);tar.addfile(item,io.BytesIO(data))
                manifest=json.dumps({"version":1,"files":{name:{"size":len(data),"sha256":"wrong"}}}).encode()
                item=tarfile.TarInfo("manifest.json");item.size=len(manifest);tar.addfile(item,io.BytesIO(manifest))
            with self.assertRaises(ValueError):restore_snapshot(Path(self.temp.name)/"empty",archive)
            self.assertFalse((Path(self.temp.name)/"escape").exists())

    def test_preflight_rejects_missing_key_secret_and_wrong_data_paths(self):
        good = {"OPENAI_API_KEY":"synthetic-test", "DEPLOYMENT_VALIDATION":"1",
            "SECRET_KEY":"s"*40,"CELERY_BROKER_URL":"redis://redis:6379/0",
            "DATABASE_URL":"sqlite:////data/app.db","SPARSE_DB_PATH":"/data/sparse_fts.db"}
        validate(good)
        for key in ("OPENAI_API_KEY","SECRET_KEY","CELERY_BROKER_URL","DATABASE_URL","SPARSE_DB_PATH"):
            with self.subTest(key=key), self.assertRaises(ValueError): validate({**good,key:""})
        with self.assertRaises(ValueError): validate({**good,"DEPLOYMENT_VALIDATION":"0"})


if __name__ == "__main__": unittest.main()
