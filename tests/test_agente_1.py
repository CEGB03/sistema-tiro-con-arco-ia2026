"""Tests del Agente 1: Clasificador/Segmentador."""

import pytest
from PIL import Image

from tiro_arco import AgenteClasificadorSegmentador


@pytest.fixture
def tmp_out(tmp_path):
    return str(tmp_path / "crops")


def test_instanciacion(tmp_out):
    agente = AgenteClasificadorSegmentador(output_dir=tmp_out)
    assert agente.output_dir == tmp_out


def test_layout_imagen_individual(tmp_out, tmp_path):
    img = Image.new("RGB", (800, 1000), color="white")
    ruta = tmp_path / "planilla_individual.png"
    img.save(ruta)

    agente = AgenteClasificadorSegmentador(output_dir=tmp_out)
    _, layout, _ = agente.analizar_layout(str(ruta))
    assert layout in ("1_arquero", "portada")


def test_procesar_documento(tmp_out, tmp_path):
    img = Image.new("RGB", (800, 1000), color="white")
    ruta = tmp_path / "planilla.png"
    img.save(ruta)

    agente = AgenteClasificadorSegmentador(output_dir=tmp_out)
    manifiesto = agente.procesar_documento(str(ruta))
    assert manifiesto["total_paginas"] == 1
    assert isinstance(manifiesto["tareas_agente2"], list)


def test_archivo_inexistente(tmp_out):
    agente = AgenteClasificadorSegmentador(output_dir=tmp_out)
    with pytest.raises(FileNotFoundError):
        agente.procesar_documento("/ruta/que/no/existe.pdf")