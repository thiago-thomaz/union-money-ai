"""UNION FINANCE AI — Central Financeira, Separação Obrigatória de 5 Estágios, Importação CSV e Conciliação (Seção 1)."""

import csv
from datetime import datetime
import io
from typing import Any, Dict, List, Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.finance.cashflow import _real_commission_query, get_cashflow_summary
from app.finance.commissions import (
    _sync_approved_commission_to_revenue_and_product,
    record_commission,
    update_commission_status,
)
from app.models.audit import AuditLog
from app.models.campaign import Campaign
from app.models.commission import Commission
from app.models.conversion import Conversion
from app.models.financial import Expense, RevenueRecord
from app.models.marketplace import Category, Marketplace
from app.models.product import Product


VALID_COMMISSION_STATUSES = {
    "POTENTIAL",
    "ATTRIBUTED",
    "PENDING",
    "APPROVED",
    "CANCELLED",
    "PAID",
}

REQUIRED_CSV_COLUMNS = {
    "external_reference",
    "date",
    "order_value",
    "commission_amount",
    "status",
}


class UnionFinanceAI:
    """Central financeira de controle de comissões, receitas, caixa efetivo e conciliação."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_five_stage_commission_separation(self) -> Dict[str, Any]:
        """Retorna a separação obrigatória entre os 5 estágios de comissão:
        1. Comissão potencial (estimada em catálogo ou status POTENTIAL)
        2. Comissão atribuída (PENDING / ATTRIBUTED)
        3. Comissão aprovada (APPROVED aguardando repasse financeiro)
        4. Comissão cancelada (CANCELLED)
        5. Comissão efetivamente paga (PAID -> Única que entra no caixa recebido)
        REGRA ETAPA 5: Exclui estritamente produtos sintéticos/teste e fontes de simulação.
        """
        catalog_potential = float(
            self.db.query(func.coalesce(func.sum(Product.estimated_commission_value), 0.0))
            .filter(Product.is_active.is_(True), Product.in_stock.is_(True), Product.is_synthetic_test.is_(False))
            .scalar()
            or 0.0
        )
        recorded_potential = float(
            _real_commission_query(self.db)
            .filter(Commission.status == "POTENTIAL")
            .scalar()
            or 0.0
        )
        potential_total = round(catalog_potential + recorded_potential, 2)

        attributed_pending = float(
            _real_commission_query(self.db)
            .filter(Commission.status.in_(["PENDING", "ATTRIBUTED"]))
            .scalar()
            or 0.0
        )
        approved_unpaid = float(
            _real_commission_query(self.db)
            .filter(Commission.status == "APPROVED")
            .scalar()
            or 0.0
        )
        cancelled = float(
            _real_commission_query(self.db)
            .filter(Commission.status == "CANCELLED")
            .scalar()
            or 0.0
        )
        effectively_paid = float(
            _real_commission_query(self.db)
            .filter(Commission.status == "PAID")
            .scalar()
            or 0.0
        )

        return {
            "stage_1_potential_commission_brl": potential_total,
            "stage_2_attributed_commission_brl": round(attributed_pending, 2),
            "stage_3_approved_commission_brl": round(approved_unpaid, 2),
            "stage_4_cancelled_commission_brl": round(cancelled, 2),
            "stage_5_paid_commission_brl": round(effectively_paid, 2),
            "cash_received_brl": round(effectively_paid, 2),
            "strict_rule": "Somente comissões reais com status PAID entram no caixa recebido (cash_received_brl). Dados sintéticos/teste jamais entram.",
        }

    def get_full_indicators(self) -> Dict[str, Any]:
        """Calcula todos os 14 indicadores exigidos na Seção 1 + separação estrita da Etapa 5."""
        stages = self.get_five_stage_commission_separation()
        cashflow = get_cashflow_summary(self.db)

        gross_commission_revenue = float(
            _real_commission_query(self.db)
            .filter(Commission.status.in_(["PENDING", "ATTRIBUTED", "APPROVED", "PAID"]))
            .scalar()
            or 0.0
        )
        total_expenses = float(
            self.db.query(func.coalesce(func.sum(Expense.amount), 0.0))
            .filter(Expense.status == "PAID")
            .scalar()
            or 0.0
        )

        real_comm_filters = (
            Product.is_synthetic_test.is_(False),
            ~Commission.source.ilike("%SYNTHETIC%"),
            ~Commission.source.ilike("%TEST%"),
            ~Commission.source.ilike("%SANDBOX%"),
            ~Commission.source.ilike("%SIMUL%"),
        )

        # Receita por marketplace (apenas comissões reais APPROVED ou PAID)
        mkt_rows = (
            self.db.query(
                Marketplace.name,
                Marketplace.slug,
                func.coalesce(func.sum(Commission.amount), 0.0).label("total"),
            )
            .join(Commission, Commission.marketplace_id == Marketplace.id)
            .join(Product, Product.id == Commission.product_id)
            .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
            .group_by(Marketplace.id)
            .all()
        )
        by_marketplace = [
            {"marketplace": r.name, "slug": r.slug, "revenue_brl": round(float(r.total), 2)}
            for r in mkt_rows
        ]

        # Receita por categoria
        cat_rows = (
            self.db.query(
                Category.name,
                Category.slug,
                func.coalesce(func.sum(Commission.amount), 0.0).label("total"),
            )
            .join(Product, Product.category_id == Category.id)
            .join(Commission, Commission.product_id == Product.id)
            .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
            .group_by(Category.id)
            .all()
        )
        by_category = [
            {"category": r.name, "slug": r.slug, "revenue_brl": round(float(r.total), 2)}
            for r in cat_rows
        ]

        # Receita por produto
        prod_rows = (
            self.db.query(
                Product.id,
                Product.title,
                func.coalesce(func.sum(Commission.amount), 0.0).label("total"),
            )
            .join(Commission, Commission.product_id == Product.id)
            .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
            .group_by(Product.id)
            .order_by(func.sum(Commission.amount).desc())
            .all()
        )
        by_product = [
            {"product_id": r.id, "title": r.title, "revenue_brl": round(float(r.total), 2)}
            for r in prod_rows
        ]

        # Receita por campanha
        camp_rows = (
            self.db.query(
                Campaign.id,
                Campaign.name,
                func.coalesce(func.sum(Commission.amount), 0.0).label("total"),
            )
            .join(Conversion, Conversion.campaign_id == Campaign.id)
            .join(Commission, Commission.conversion_id == Conversion.id)
            .join(Product, Product.id == Commission.product_id)
            .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
            .group_by(Campaign.id)
            .all()
        )
        by_campaign = [
            {"campaign_id": r.id, "campaign": r.name, "revenue_brl": round(float(r.total), 2)}
            for r in camp_rows
        ]

        # Receita por canal
        chan_rows = (
            self.db.query(
                Conversion.channel,
                func.coalesce(func.sum(Commission.amount), 0.0).label("total"),
            )
            .join(Commission, Commission.conversion_id == Conversion.id)
            .join(Product, Product.id == Commission.product_id)
            .filter(Commission.status.in_(["APPROVED", "PAID"]), *real_comm_filters)
            .group_by(Conversion.channel)
            .all()
        )
        by_channel = [
            {"channel": r.channel or "DIRECT", "revenue_brl": round(float(r.total), 2)}
            for r in chan_rows
        ]

        # Conversões reais separadas por status vs conversões de teste (ETAPA 5)
        real_conv_filters = (
            Product.is_synthetic_test.is_(False),
            ~Conversion.source.ilike("%SYNTHETIC%"),
            ~Conversion.source.ilike("%TEST%"),
            ~Conversion.source.ilike("%SANDBOX%"),
            ~Conversion.source.ilike("%SIMUL%"),
        )
        pending_conversions_count = int(
            self.db.query(func.count(Conversion.id))
            .join(Product, Product.id == Conversion.product_id)
            .filter(Conversion.status.in_(["PENDING", "ATTRIBUTED"]), *real_conv_filters)
            .scalar()
            or 0
        )
        approved_conversions_count = int(
            self.db.query(func.count(Conversion.id))
            .join(Product, Product.id == Conversion.product_id)
            .filter(Conversion.status == "CONFIRMED", *real_conv_filters)
            .scalar()
            or 0
        )

        paid_commissions = stages["stage_5_paid_commission_brl"]
        approved_and_paid = round(
            stages["stage_3_approved_commission_brl"] + stages["stage_5_paid_commission_brl"], 2
        )
        net_result_paid = round(paid_commissions - total_expenses, 2)

        strict_financial_separation = {
            "test_synthetic_data_brl": cashflow["test_synthetic_commissions_excluded_brl"],
            "test_synthetic_conversions_count": cashflow["test_synthetic_conversions_excluded_count"],
            "test_synthetic_included_in_revenue": False,
            "pending_conversions_count": pending_conversions_count,
            "approved_conversions_count": approved_conversions_count,
            "estimated_commissions_brl": stages["stage_1_potential_commission_brl"],
            "confirmed_commissions_brl": stages["stage_3_approved_commission_brl"],
            "effectively_paid_brl": paid_commissions,
        }

        return {
            "gross_commission_revenue_brl": round(gross_commission_revenue, 2),
            "estimated_commissions_brl": stages["stage_1_potential_commission_brl"],
            "pending_commissions_brl": stages["stage_2_attributed_commission_brl"],
            "approved_only_commissions_brl": stages["stage_3_approved_commission_brl"],
            "approved_commissions_brl": approved_and_paid,
            "cancelled_commissions_brl": stages["stage_4_cancelled_commission_brl"],
            "paid_commissions_brl": paid_commissions,
            "expenses_brl": round(total_expenses, 2),
            "net_result_brl": cashflow["net_cashflow_brl"],
            "net_cash_received_brl": net_result_paid,
            "cash_received_brl": paid_commissions,
            "five_stage_separation": stages,
            "strict_financial_separation": strict_financial_separation,
            "cashflow": cashflow,
            "revenue_by_marketplace": by_marketplace,
            "revenue_by_category": by_category,
            "revenue_by_product": by_product,
            "revenue_by_campaign": by_campaign,
            "revenue_by_channel": by_channel,
        }

    def import_official_csv_report(
        self,
        csv_content: str,
        marketplace_slug: str = "mercadolivre",
    ) -> Dict[str, Any]:
        """Importa e valida relatório CSV oficial de marketplace com conciliação automática.

        Valida:
        - Colunas obrigatórias (external_reference, date, order_value, commission_amount, status)
        - Datas válidas (YYYY-MM-DD ou ISO-8601)
        - Valores numéricos não negativos
        - Identificadores (external_reference não vazio e produto válido)
        - Duplicidade (ignora linhas idênticas já importadas ou concilia mudança de status)
        - Status permitidos (POTENTIAL, ATTRIBUTED, PENDING, APPROVED, CANCELLED, PAID)
        - Integridade dos registros
        """
        if not csv_content or not csv_content.strip():
            raise ValueError("Conteúdo CSV vazio.")

        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        if not reader.fieldnames:
            raise ValueError("Cabeçalho CSV ausente ou inválido.")

        normalized_headers = {h.strip().lower() for h in reader.fieldnames if h}
        missing_cols = REQUIRED_CSV_COLUMNS - normalized_headers
        if missing_cols:
            raise ValueError(
                f"Colunas obrigatórias ausentes no CSV: {', '.join(sorted(missing_cols))}"
            )

        mkt = (
            self.db.query(Marketplace)
            .filter(Marketplace.slug == marketplace_slug.lower().strip())
            .first()
        )
        if not mkt:
            mkt = self.db.query(Marketplace).first()
        if not mkt:
            raise ValueError("Nenhum marketplace cadastrado no banco para associar o CSV.")

        imported_count = 0
        updated_reconciled_count = 0
        duplicate_skipped_count = 0
        errors: List[Dict[str, Any]] = []
        processed_refs_in_batch: set[str] = set()

        for row_idx, raw_row in enumerate(reader, start=2):
            row = {
                (k.strip().lower() if k else ""): (v.strip() if isinstance(v, str) else "")
                for k, v in raw_row.items()
            }
            ext_ref = row.get("external_reference", "")
            date_str = row.get("date", "")
            order_val_str = row.get("order_value", "")
            comm_val_str = row.get("commission_amount", "")
            status_str = row.get("status", "").upper()
            prod_id_str = row.get("product_id", "")

            # 1. Validação de identificador
            if not ext_ref:
                errors.append({"line": row_idx, "error": "external_reference vazio"})
                continue

            # 2. Validação de data
            parsed_date: Optional[datetime] = None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
                try:
                    parsed_date = datetime.strptime(date_str[:19], fmt)
                    break
                except ValueError:
                    continue
            if not parsed_date:
                errors.append({"line": row_idx, "external_reference": ext_ref, "error": f"Data inválida: {date_str}"})
                continue

            # 3. Validação de valores numéricos
            try:
                order_value = float(order_val_str.replace(",", "."))
                commission_amount = float(comm_val_str.replace(",", "."))
                if order_value <= 0 or commission_amount < 0 or commission_amount > order_value:
                    raise ValueError("Valores fora do intervalo comercial válido")
            except ValueError as exc:
                errors.append({"line": row_idx, "external_reference": ext_ref, "error": f"Valor inválido: {exc}"})
                continue

            # 4. Validação de status
            if status_str not in VALID_COMMISSION_STATUSES:
                errors.append({"line": row_idx, "external_reference": ext_ref, "error": f"Status inválido: {status_str}"})
                continue

            # 5. Verifica duplicidade no próprio arquivo
            batch_key = f"{ext_ref}:{status_str}:{commission_amount:.2f}"
            if batch_key in processed_refs_in_batch:
                duplicate_skipped_count += 1
                continue
            processed_refs_in_batch.add(batch_key)

            # 6. Resolve produto
            product: Optional[Product] = None
            if prod_id_str and prod_id_str.isdigit():
                product = self.db.query(Product).filter(Product.id == int(prod_id_str)).first()
            if not product:
                product = (
                    self.db.query(Product)
                    .filter(Product.marketplace_id == mkt.id, Product.is_active.is_(True))
                    .first()
                ) or self.db.query(Product).first()
            if not product:
                errors.append({"line": row_idx, "external_reference": ext_ref, "error": "Nenhum produto encontrado para vincular."})
                continue

            # 7. Verifica existência prévia para deduplicação ou conciliação de status
            existing_comm = (
                self.db.query(Commission)
                .filter(Commission.external_reference == ext_ref)
                .first()
            )
            if existing_comm:
                if existing_comm.status == status_str and round(existing_comm.amount, 2) == round(commission_amount, 2):
                    duplicate_skipped_count += 1
                    continue
                else:
                    update_commission_status(
                        db=self.db,
                        commission_id=existing_comm.id,
                        new_status=status_str,
                        reason=f"Conciliação via importação CSV oficial ({mkt.slug})",
                        new_amount=commission_amount,
                    )
                    updated_reconciled_count += 1
                    continue

            # 8. Cria nova conversão + comissão se não for meramente POTENTIAL
            effective_rate = round((commission_amount / order_value) * 100.0, 2) if order_value > 0 else 0.0
            conv_id: Optional[int] = None
            if status_str != "POTENTIAL":
                conv = Conversion(
                    product_id=product.id,
                    marketplace_id=mkt.id,
                    source=f"CSV_OFICIAL_{mkt.slug.upper()}",
                    channel="CSV_IMPORT",
                    content_format="OFFICIAL_REPORT",
                    status="CONFIRMED" if status_str in ("APPROVED", "PAID") else status_str,
                    order_value=round(order_value, 2),
                    quantity=1,
                    external_reference=ext_ref,
                )
                self.db.add(conv)
                self.db.flush()
                conv_id = conv.id

            record_commission(
                db=self.db,
                product_id=product.id,
                marketplace_id=mkt.id,
                source=f"CSV_OFICIAL_{mkt.slug.upper()}",
                amount=round(commission_amount, 2),
                status=status_str,
                conversion_id=conv_id,
                announced_rate_pct=product.announced_commission_rate,
                effective_rate_pct=effective_rate,
                external_reference=ext_ref,
            )
            imported_count += 1

        self.db.add(
            AuditLog(
                actor="admin",
                action="IMPORT_OFFICIAL_CSV_REPORT",
                entity_type="Commission",
                entity_id=marketplace_slug,
                details={
                    "imported": imported_count,
                    "reconciled": updated_reconciled_count,
                    "duplicates_skipped": duplicate_skipped_count,
                    "errors_count": len(errors),
                },
            )
        )
        self.db.commit()

        return {
            "marketplace_slug": mkt.slug,
            "imported_count": imported_count,
            "updated_reconciled_count": updated_reconciled_count,
            "duplicate_skipped_count": duplicate_skipped_count,
            "errors": errors,
            "is_valid_import": len(errors) == 0,
        }

    def reconcile_commissions(self) -> Dict[str, Any]:
        """Executa conciliação financeira entre Comissões, Receitas Confirmadas e Caixa Efetivo."""
        all_commissions = self.db.query(Commission).all()
        synced_revenues = 0
        discrepancies: List[Dict[str, Any]] = []

        for comm in all_commissions:
            if comm.status in ("APPROVED", "PAID"):
                existing_rev = (
                    self.db.query(RevenueRecord)
                    .filter(RevenueRecord.commission_id == comm.id)
                    .first()
                )
                if not existing_rev:
                    _sync_approved_commission_to_revenue_and_product(self.db, comm)
                    synced_revenues += 1
                elif round(existing_rev.amount, 2) != round(comm.amount, 2):
                    existing_rev.amount = round(comm.amount, 2)
                    synced_revenues += 1
            elif comm.status in ("POTENTIAL", "PENDING", "ATTRIBUTED", "CANCELLED"):
                # Garante que comissões não aprovadas ou canceladas não constem como CONFIRMED
                wrong_rev = (
                    self.db.query(RevenueRecord)
                    .filter(RevenueRecord.commission_id == comm.id, RevenueRecord.status == "CONFIRMED")
                    .first()
                )
                if wrong_rev:
                    wrong_rev.status = "REVERSED"
                    discrepancies.append(
                        {
                            "commission_uid": comm.uid,
                            "status": comm.status,
                            "action_taken": "REVENUE_REVERSED",
                        }
                    )

        self.db.commit()
        stages = self.get_five_stage_commission_separation()
        return {
            "status": "RECONCILED",
            "total_commissions_checked": len(all_commissions),
            "synced_revenues": synced_revenues,
            "discrepancies_resolved": discrepancies,
            "five_stage_separation": stages,
        }
