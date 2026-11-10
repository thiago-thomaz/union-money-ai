"""Conformidade com Plataformas, Marketplaces e Canais — Checklist Auditável e Validade Periódica (Seção 5)."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.audit import AuditLog
from app.models.compliance import CompliancePolicyRecord


class UnionCompliance:
    """Gerencia checklists de conformidade, validade temporal de revisões e bloqueio de recursos não autorizados."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _has_external_credentials(slug: str) -> bool:
        """Verifica se uma integração externa possui credenciais configuradas no ambiente."""
        s = slug.lower().strip()
        if s == "site":
            return True
        if s == "mercadolivre":
            return bool(settings.ML_APP_ID and settings.ML_CLIENT_SECRET)
        if s == "amazon":
            return bool(settings.AMAZON_ACCESS_KEY and settings.AMAZON_SECRET_KEY and settings.AMAZON_PARTNER_TAG)
        if s == "shopee":
            return bool(settings.SHOPEE_APP_ID and settings.SHOPEE_APP_SECRET)
        if s == "youtube":
            return bool(settings.YOUTUBE_API_KEY)
        if s == "instagram":
            return bool(settings.INSTAGRAM_ACCESS_TOKEN)
        if s == "pinterest":
            return bool(settings.PINTEREST_ACCESS_TOKEN)
        return False

    def is_verification_expired(self, record: CompliancePolicyRecord) -> bool:
        """Verifica se a revisão manual das políticas expirou conforme validity_days."""
        if not record.last_verified_at:
            return True
        last_dt = record.last_verified_at
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        expiry = last_dt + timedelta(days=max(1, record.validity_days or 90))
        return datetime.now(timezone.utc) > expiry

    def list_checklist(self) -> List[Dict[str, Any]]:
        """Lista todos os registros de conformidade sincronizando o status de credenciais externas."""
        records = self.db.query(CompliancePolicyRecord).order_by(CompliancePolicyRecord.id.asc()).all()
        output: List[Dict[str, Any]] = []

        for r in records:
            has_creds = self._has_external_credentials(r.target_slug)
            expired = self.is_verification_expired(r)
            terms_accepted = bool(r.eligibility_verified and r.publishing_rules_verified)
            is_blocked = not bool(r.is_integration_enabled)

            # Regra obrigatória: integrações externas sem credenciais configuradas devem aparecer como PENDENTE, nunca APROVADA
            if is_blocked:
                effective_status = "BLOQUEADA"
            elif r.target_slug != "site" and not has_creds:
                effective_status = "PENDENTE"
            elif terms_accepted and r.authorization_verified:
                effective_status = "APROVADA"
            else:
                effective_status = "PENDENTE"

            can_operate = (
                terms_accepted
                and not is_blocked
                and not expired
                and effective_status == "APROVADA"
            )

            output.append(
                {
                    "id": r.id,
                    "target_type": r.target_type,
                    "target_slug": r.target_slug,
                    "target_name": r.target_name,
                    "terms_accepted": terms_accepted,
                    "affiliate_disclosure_required": bool(r.disclosure_rules_verified),
                    "publication_rules": r.notes or "Regras oficiais da plataforma verificadas.",
                    "daily_limit": 20 if r.target_slug == "site" else 5,
                    "link_restrictions": "Apenas links rastreáveis oficiais permitidos.",
                    "image_restrictions": "Somente imagens autorizadas do produto ou ilustrativas próprias.",
                    "price_restrictions": "Exibir aviso de que preço e estoque podem variar.",
                    "is_feature_blocked": is_blocked,
                    "has_external_credentials": has_creds,
                    "integration_status": effective_status,
                    "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
                    "validity_days": r.validity_days,
                    "is_verification_expired": expired,
                    "needs_periodic_review": expired or not terms_accepted,
                    "authorized_to_operate": can_operate,
                }
            )
        return output

    def verify_or_update_policy(
        self,
        target_slug: str,
        terms_accepted: Optional[bool] = None,
        is_feature_blocked: Optional[bool] = None,
        daily_limit: Optional[int] = None,
        validity_days: Optional[int] = None,
        mark_verified_now: bool = True,
        actor: str = "admin",
    ) -> Dict[str, Any]:
        """Atualiza o checklist de um marketplace/canal respeitando a regra de credenciais externas."""
        slug = target_slug.lower().strip()
        rec = (
            self.db.query(CompliancePolicyRecord)
            .filter(CompliancePolicyRecord.target_slug == slug)
            .first()
        )
        if not rec:
            raise ValueError(f"Registro de conformidade '{slug}' não encontrado.")

        has_creds = self._has_external_credentials(slug)
        if terms_accepted is not None:
            rec.eligibility_verified = bool(terms_accepted)
            rec.publishing_rules_verified = bool(terms_accepted)
            # Só marca authorization_verified se tiver credenciais externas (ou for o site próprio)
            rec.authorization_verified = bool(terms_accepted) and (slug == "site" or has_creds)
        if is_feature_blocked is not None:
            rec.is_integration_enabled = not bool(is_feature_blocked)
        if validity_days is not None and validity_days >= 1:
            rec.validity_days = int(validity_days)
        if mark_verified_now:
            rec.last_verified_at = datetime.now(timezone.utc)

        self.db.add(
            AuditLog(
                actor=actor,
                action="UPDATE_COMPLIANCE_POLICY",
                entity_type="CompliancePolicyRecord",
                entity_id=slug,
                details={
                    "eligibility_verified": rec.eligibility_verified,
                    "is_integration_enabled": rec.is_integration_enabled,
                    "has_external_credentials": has_creds,
                },
            )
        )
        self.db.commit()
        items = [x for x in self.list_checklist() if x["target_slug"] == slug]
        return items[0]
