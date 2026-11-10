"""Motor de Produção Automática de Vídeos (UNION VIDEO ENGINE - Seção 4).

Características:
- Formatos: 9:16 (720x1280 vertical), 16:9 (1280x720 horizontal), 1:1 (1080x1080 quadrado).
- Estrutura narrativa de 7 etapas:
  1. Abertura que desperte interesse (Hook)
  2. Problema do consumidor
  3. Apresentação da solução
  4. Características verificadas
  5. Benefícios explicados
  6. Chamada para conhecer o produto (CTA)
  7. Identificação de publicidade e afiliado
- Gera composição gráfica original com Pillow (sem usar imagens não autorizadas e sem remover marcas d'água).
- Gera legendas sincronizadas (.srt).
- Renderiza arquivo MP4 real com FFmpeg e valida integridade do binário MP4 antes de aprovar.
"""

from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Tuple
from PIL import Image, ImageDraw
from app.config import settings
from app.content_engine.seo import slugify
from app.content_engine.thumbnails import generate_product_thumbnail

ASPECT_DIMENSIONS: Dict[str, Tuple[int, int]] = {
    "9:16": (720, 1280),
    "16:9": (1280, 720),
    "1:1": (1080, 1080),
}


class UnionVideoEngine:
    """Motor de criação e validação de vídeos curtos em múltiplos formatos (9:16, 16:9, 1:1)."""

    @staticmethod
    def resolve_ffmpeg_binary() -> str | None:
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            return ffmpeg_bin
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    @classmethod
    def build_7_step_scenes(
        cls,
        product_title: str,
        price: float,
        marketplace_name: str,
        category_name: str = "Geral",
        verified_features: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Constrói as 7 cenas obrigatórias do vídeo sem simular experiência pessoal inexistente."""
        price_str = f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        features_text = (
            verified_features.strip()
            if verified_features and verified_features.strip()
            else f"Categoria {category_name} • Preço verificado: {price_str} (confira a ficha completa na loja)."
        )
        return [
            {
                "step": 1,
                "label": "ABERTURA",
                "headline": f"Buscando {category_name} com bom custo-benefício?",
                "subtext": f"Análise objetiva de oferta no {marketplace_name}",
                "duration_sec": 2,
            },
            {
                "step": 2,
                "label": "PROBLEMA DO CONSUMIDOR",
                "headline": "Difícil comparar preços e especificações confiáveis?",
                "subtext": "Reunimos os dados verificados para facilitar sua escolha.",
                "duration_sec": 2,
            },
            {
                "step": 3,
                "label": "APRESENTAÇÃO DA SOLUÇÃO",
                "headline": product_title[:90],
                "subtext": f"Disponível na plataforma oficial {marketplace_name}",
                "duration_sec": 2,
            },
            {
                "step": 4,
                "label": "CARACTERÍSTICAS VERIFICADAS",
                "headline": f"Valor consultado: {price_str}",
                "subtext": features_text[:110],
                "duration_sec": 2,
            },
            {
                "step": 5,
                "label": "BENEFÍCIOS EXPLICADOS",
                "headline": "Relação utilidade x preço analisada",
                "subtext": "Compra processada diretamente no ambiente seguro do marketplace.",
                "duration_sec": 2,
            },
            {
                "step": 6,
                "label": "CHAMADA PARA AÇÃO",
                "headline": f"Consulte estoque e condições no {marketplace_name}",
                "subtext": "Acesse o link verificado na descrição ou página.",
                "duration_sec": 2,
            },
            {
                "step": 7,
                "label": "TRANSPARÊNCIA COMERCIAL",
                "headline": "PUBLICIDADE • LINK DE AFILIADO",
                "subtext": "Podemos receber comissão por compras qualificadas, sem custo extra para você.",
                "duration_sec": 2,
            },
        ]

    @classmethod
    def render_scene_frame(
        cls,
        scene: Dict[str, Any],
        width: int,
        height: int,
        output_path: Path,
    ) -> Path:
        """Renderiza composição gráfica original e legível com Pillow para uma cena do vídeo."""
        img = Image.new("RGB", (width, height), color=(11, 17, 32))
        draw = ImageDraw.Draw(img)

        # Moldura externa e barra superior
        pad = 28
        draw.rectangle([(pad, pad), (width - pad, height - pad)], outline=(16, 185, 129), width=5)
        draw.rectangle([(pad + 20, pad + 20), (width - pad - 20, pad + 84)], fill=(16, 185, 129))
        draw.text(
            (pad + 38, pad + 42),
            f"ETAPA {scene['step']}/7 • {scene['label']}",
            fill=(11, 17, 32),
        )

        # Quebra de linha adaptativa conforme largura
        max_chars = 30 if width <= 720 else 46

        def _wrap(txt: str, limit: int) -> List[str]:
            words = txt.split()
            lines, curr = [], ""
            for w in words:
                if len(curr) + len(w) + 1 <= limit:
                    curr = f"{curr} {w}".strip()
                else:
                    lines.append(curr)
                    curr = w
            if curr:
                lines.append(curr)
            return lines

        center_y = int(height * 0.34)
        for line in _wrap(scene["headline"], max_chars)[:4]:
            draw.text((pad + 36, center_y), line, fill=(248, 250, 252))
            center_y += 46

        center_y += 24
        for line in _wrap(scene["subtext"], max_chars + 6)[:4]:
            draw.text((pad + 36, center_y), line, fill=(52, 211, 153))
            center_y += 36

        # Rodapé permanente de identificação publicitária
        draw.rectangle(
            [(pad + 20, height - pad - 85), (width - pad - 20, height - pad - 20)],
            fill=(30, 41, 59),
            outline=(51, 65, 85),
            width=2,
        )
        draw.text(
            (pad + 36, height - pad - 60),
            "UNION OFERTAS | PUBLICIDADE • LINK DE AFILIADO OFICIAL",
            fill=(148, 163, 184),
        )

        img.save(output_path, format="PNG")
        return output_path

    @classmethod
    def write_synchronized_srt(cls, scenes: List[Dict[str, Any]], srt_path: Path) -> Path:
        """Gera arquivo de legendas sincronizadas (.srt) correspondente às 7 cenas."""
        def _fmt_time(sec: int) -> str:
            hrs = sec // 3600
            mins = (sec % 3600) // 60
            secs = sec % 60
            return f"{hrs:02d}:{mins:02d}:{secs:02d},000"

        blocks = []
        elapsed = 0
        for idx, sc in enumerate(scenes, start=1):
            dur = int(sc.get("duration_sec", 2))
            start_t = _fmt_time(elapsed)
            end_t = _fmt_time(elapsed + dur)
            elapsed += dur
            blocks.append(f"{idx}\n{start_t} --> {end_t}\n{sc['headline']} - {sc['subtext']}\n")

        srt_path.write_text("\n".join(blocks), encoding="utf-8")
        return srt_path

    @staticmethod
    def validate_mp4_file(video_path: Path) -> bool:
        """Valida que o arquivo de vídeo foi gerado, possui tamanho > 1 KB e assinatura MP4 'ftyp'."""
        if not video_path.exists() or video_path.stat().st_size < 1024:
            return False
        with video_path.open("rb") as f:
            header = f.read(32)
        return b"ftyp" in header

    @classmethod
    def generate_video(
        cls,
        product_title: str,
        price: float,
        marketplace_name: str,
        aspect_ratio: str = "9:16",
        category_name: str = "Geral",
        verified_features: str | None = None,
    ) -> Dict[str, Any]:
        """Produz vídeo completo com 7 cenas, legendas .srt e validação de arquivo MP4."""
        ratio = aspect_ratio if aspect_ratio in ASPECT_DIMENSIONS else "9:16"
        width, height = ASPECT_DIMENSIONS[ratio]
        ratio_slug = ratio.replace(":", "x")
        base_slug = f"{slugify(product_title)[:35]}-{ratio_slug}"

        scenes = cls.build_7_step_scenes(
            product_title=product_title,
            price=price,
            marketplace_name=marketplace_name,
            category_name=category_name,
            verified_features=verified_features,
        )

        videos_dir = settings.storage_dir / "videos"
        thumbs_dir = settings.storage_dir / "thumbnails"

        srt_path = videos_dir / f"subtitles-{base_slug}.srt"
        cls.write_synchronized_srt(scenes, srt_path)

        # Renderiza quadros de cada cena e concatena via arquivo concat do FFmpeg
        frame_paths: List[Path] = []
        for sc in scenes:
            frame_file = thumbs_dir / f"frame-{base_slug}-s{sc['step']}.png"
            cls.render_scene_frame(sc, width, height, frame_file)
            frame_paths.append(frame_file)

        video_path = videos_dir / f"video-{base_slug}.mp4"
        ffmpeg_bin = cls.resolve_ffmpeg_binary()
        if not ffmpeg_bin:
            return {
                "status": "THUMBNAIL_AND_SRT_ONLY",
                "validated": False,
                "aspect_ratio": ratio,
                "thumbnail_path": str(frame_paths[0]),
                "subtitle_path": str(srt_path),
                "video_path": None,
                "scenes_count": len(scenes),
                "message": "FFmpeg não localizado; frames e legendas sincronizadas gerados.",
            }

        concat_file = videos_dir / f"concat-{base_slug}.txt"
        concat_lines = []
        for fp, sc in zip(frame_paths, scenes):
            concat_lines.append(f"file '{fp.as_posix()}'")
            concat_lines.append(f"duration {int(sc['duration_sec'])}")
        concat_lines.append(f"file '{frame_paths[-1].as_posix()}'")
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vsync",
            "vfr",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(video_path),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            is_valid = cls.validate_mp4_file(video_path)
            return {
                "status": "VIDEO_VALIDATED" if is_valid else "VIDEO_VALIDATION_FAILED",
                "validated": is_valid,
                "aspect_ratio": ratio,
                "dimensions": f"{width}x{height}",
                "thumbnail_path": str(frame_paths[0]),
                "subtitle_path": str(srt_path),
                "video_path": str(video_path) if is_valid else None,
                "scenes_count": len(scenes),
                "message": "Vídeo MP4 de 7 etapas renderizado e validado com sucesso.",
            }
        except Exception as exc:
            return {
                "status": "THUMBNAIL_AND_SRT_ONLY",
                "validated": False,
                "aspect_ratio": ratio,
                "thumbnail_path": str(frame_paths[0]),
                "subtitle_path": str(srt_path),
                "video_path": None,
                "scenes_count": len(scenes),
                "message": f"Frames e legendas gerados; falha ao codificar MP4 ({exc}).",
            }
        finally:
            if concat_file.exists():
                try:
                    concat_file.unlink()
                except OSError:
                    pass


def generate_short_video_asset(
    product_title: str,
    price: float,
    marketplace_name: str,
    duration_seconds: int = 5,
    aspect_ratio: str = "16:9",
) -> Dict[str, Any]:
    """Função compatível com a Parte 1 que delega para o UNION VIDEO ENGINE."""
    _ = generate_product_thumbnail(product_title, price, marketplace_name)
    res = UnionVideoEngine.generate_video(
        product_title=product_title,
        price=price,
        marketplace_name=marketplace_name,
        aspect_ratio=aspect_ratio,
    )
    return {
        "status": "VIDEO_GENERATED" if res["validated"] else "THUMBNAIL_ONLY",
        "validated": res["validated"],
        "aspect_ratio": res["aspect_ratio"],
        "thumbnail_path": res["thumbnail_path"],
        "subtitle_path": res["subtitle_path"],
        "video_path": res["video_path"],
        "message": res["message"],
    }
