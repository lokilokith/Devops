import os
from dotenv import load_dotenv
load_dotenv(".env")

from app import create_app
from app.extensions import db
from app.vault.service import VaultApplicationService
from app.vault.domain import SecretDomainService
from app.vault.crypto import EncryptionService, LocalEnvironmentKeyProvider
from app.vault.repository import SqlAlchemyVaultRepository
from app.policy_engine.engine import PolicyEngine
from app.audit.service import AuditService
from app.audit.repository import AuditRepository
from app.authorization.service import AuthorizationService
from uuid import UUID
import psycopg2

app = create_app()
with app.app_context():
    service = VaultApplicationService(
        domain_service=SecretDomainService(),
        encryption_service=EncryptionService(LocalEnvironmentKeyProvider()),
        repository=SqlAlchemyVaultRepository(db.session),
        policy_engine=PolicyEngine(db.session, AuthorizationService(db.session)),
        audit_service=AuditService(AuditRepository(db.session)),
        authz_service=AuthorizationService(db.session),
        session=db.session,
    )
    
    # get a user id
    conn = psycopg2.connect('postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db')
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username LIKE 'rbac_sec_admin%' LIMIT 1")
    uid_str = cur.fetchone()[0]
    uid = UUID(uid_str)
    
    cur.execute("SELECT id FROM resources LIMIT 1")
    rid_str = cur.fetchone()[0]
    rid = UUID(rid_str)
    conn.close()
    
    try:
        service.create_secret(uid, rid, b"test")
        print("Success")
    except Exception as e:
        print("Caught Exception:", type(e), e)

    db.session.commit()
    
    conn = psycopg2.connect('postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db')
    cur = conn.cursor()
    cur.execute("SELECT action FROM audit_logs WHERE action = 'SECRET_CREATE_FAILED'")
    print("In DB:", cur.fetchall())
    conn.close()
