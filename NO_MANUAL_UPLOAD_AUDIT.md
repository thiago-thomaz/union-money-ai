# AUDITORIA DE ELIMINAÇÃO DE UPLOAD E TAREFAS MANUAIS (`NO_MANUAL_UPLOAD_AUDIT.md`)

**Sistema:** UNION MONEY AI — Fase 4 (Autonomia Total e Operação Comercial 24/7)  
**Objetivo:** Comprovar tecnicamente que nenhuma das 8 frentes operacionais recorrentes exige cadastro manual, planilhas, cópia manual de links ou upload/download manual de arquivos.

---

## Matriz de Verificação das 8 Frentes Sem Ação Manual Recorrente

| # | Frente Operacional | Módulo Python Responsável | Como Opera Sem Intervenção Manual | Status |
|---|---|---|---|---|
| 1 | **Descoberta de produtos sem cadastro manual** | `app/intelligence/autonomous_discovery.py` (`AutonomousProductDiscovery`) | Executa buscas incrementais por palavras-chave comerciais dos nichos ativos (`Category`) usando `MercadoLivreConnector`, `AmazonConnector` e `ShopeeConnector`. Dedup por `(marketplace_id, external_id)` e validação de preço/título/URL antes de persistir no banco. | **100% AUTOMÁTICO** |
| 2 | **Atualização de produtos sem planilhas** | `app/intelligence/autonomous_discovery.py` (`suspend_invalid_or_uninteresting_products`) | A cada ciclo de 6 horas, revalida disponibilidade, estoque, preço > 0 e comissão estimada. Produtos indisponíveis ou fora dos critérios têm `is_active=False` e campanhas pausadas sem planilhas. | **100% AUTOMÁTICO** |
| 3 | **Links de afiliados sem copiar e colar** | `app/marketing/link_manager.py` (`auto_generate_or_update_link_for_product`) | Constrói automaticamente a URL oficial de afiliado parametrizada (`matt_tool`, `tag`, `af_siteid`, UTMs) e o slug `/r/{code}` assim que o produto é descoberto ou atualizado. Se o marketplace exigir tag oficial não configurada, marca `PENDING_AFFILIATE_AUTH` em vez de gerar link falso. | **100% AUTOMÁTICO** |
| 4 | **Conteúdo editorial sem redação manual** | `app/content_engine/autonomous_pipeline.py` (`AutonomousContentPipeline`) | Máquina de estados de 9 estágios (`DISCOVERY -> ANALYSIS -> SCRIPT -> CONTENT -> QUALITY_CHECK -> SEO -> READY -> PUBLISHED -> MONITORING`) gera artigo SEO, comparativo, roteiro e copy, validando score editorial >= 70 e aviso obrigatório de afiliado. | **100% AUTOMÁTICO** |
| 5 | **Vídeos curtos sem edição manual** | `app/video_engine/union_video_engine.py` integrado ao `AutonomousContentPipeline` | Renderiza automaticamente vídeos verticais 9:16 (`.mp4` via FFmpeg/Pillow), narração (`.wav`) e legendas sincronizadas (`.srt`) diretamente no diretório `storage/videos/` durante o estágio `CONTENT`. | **100% AUTOMÁTICO** |
| 6 | **Imagens e miniaturas sem upload manual** | `app/content_engine/union_content_engine.py` | Gera programaticamente via `Pillow` imagens ilustrativas (`1200x630` e `1000x1500` para Pinterest) e thumbnails de alto contraste (`1280x720`), vinculando `media_path` diretamente ao registro `ContentItem`. | **100% AUTOMÁTICO** |
| 7 | **Publicações multicanal sem ação humana recorrente** | `app/marketing/multichannel_publisher.py` (`MultiChannelAutoPublisher`) | Publica imediatamente no portal próprio `UNION OFERTAS` (`ACTIVE`) e, nos canais externos (`YouTube`, `Instagram`, `Pinterest`), valida formato/dimensões/aviso de afiliado e dispara a API oficial quando `UNION CONNECT` está `ACTIVE` (ou registra `BLOQUEADA POR AUTORIZAÇÃO` sem fingir postagem). | **100% AUTOMÁTICO** |
| 8 | **Relatórios e comissões sem upload manual de CSV** | `app/finance/auto_sales_tracker.py` (`AutoSalesTracker`) | Sincroniza vendas e comissões via: (a) API oficial de relatórios (`Shopee Affiliate GraphQL`), (b) API oficial de pedidos (`Mercado Livre /orders/search`), (c) Webhooks assinados HMAC-SHA256 (`POST /api/webhooks/conversions/{slug}`), e (d) Leitor de relatórios por e-mail IMAP OAuth somente leitura. O importador CSV da Fase 3 permanece apenas como contingência opcional. | **100% AUTOMÁTICO** |

---

## Conclusão da Auditoria

- **Intervenção inicial única exigida do proprietário:** Autorizar as contas no `UNION CONNECT` (OAuth2 / chaves de API e tags de afiliado no `.env` ou via `/api/connect/token/{slug}`).
- **Intervenção manual recorrente após ativação:** **ZERO.**

