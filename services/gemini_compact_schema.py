"""Esquema JSON compacto para Gemini 3.x.

Se usa un arreglo uniforme de valores, en lugar de 8 objetos anidados
Pydantic con $defs y additionalProperties. La validación semántica se hace
localmente con ExtraccionContrato (sin relajar controles de auditoría).
"""
from __future__ import annotations

import json
from typing import Any

from services.contract_schema import DatoConEvidencia, ExtraccionContrato

CAMPOS_CONTRATO = (
    "numero_contrato",
    "nombre_obra",
    "contratista",
    "fecha_firma",
    "fecha_inicio",
    "fecha_termino",
    "monto_con_iva",
    "porcentaje_anticipo",
)

# Evitar referencias y restricciones innecesarias: Google documenta errores
# HTTP 400 ante esquemas anidados/complejos. Aquí hay una sola estructura
# reutilizada en un arreglo sin maxItems, ge, default ni additionalProperties.
GEMINI_COMPACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "campos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "campo": {"type": "string"},
                    "valor": {"type": ["string", "null"]},
                    "pagina": {"type": ["integer", "null"]},
                    "evidencia": {"type": ["string", "null"]},
                },
                "required": ["campo", "valor", "pagina", "evidencia"],
            },
        },
        "observaciones": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["campos", "observaciones"],
}


def convertir_respuesta_compacta(payload: str | dict[str, Any]) -> ExtraccionContrato:
    """Rechaza campos inesperados o duplicados; documenta valores ausentes.

    La ausencia de un dato se registra con valor null y debe ser revisada.
    Un formato ininteligible NO se guarda como extracción exitosa.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Gemini no devolvió un JSON válido.") from exc
    elif isinstance(payload, dict):
        data = payload
    else:
        raise ValueError("La respuesta de Gemini no tiene formato JSON.")

    if not isinstance(data, dict) or set(data) != {"campos", "observaciones"}:
        raise ValueError("La estructura principal del resultado es inválida.")
    campos = data["campos"]
    observaciones = data["observaciones"]
    if not isinstance(campos, list) or len(campos) > len(CAMPOS_CONTRATO):
        raise ValueError("Cantidad inesperada de campos en la extracción.")
    if not isinstance(observaciones, list) or len(observaciones) > 30:
        raise ValueError("Observaciones inválidas en la extracción.")
    if any(not isinstance(x, str) for x in observaciones):
        raise ValueError("Las observaciones deben ser texto.")

    encontrados: dict[str, DatoConEvidencia] = {}
    for item in campos:
        if not isinstance(item, dict) or set(item) != {
            "campo", "valor", "pagina", "evidencia"
        }:
            raise ValueError("Estructura de campo desconocida.")
        nombre = item["campo"]
        if not isinstance(nombre, str) or nombre not in CAMPOS_CONTRATO:
            raise ValueError("Gemini devolvió un nombre de campo no admitido.")
        if nombre in encontrados:
            raise ValueError("Gemini repitió un campo con valores contradictorios.")
        encontrados[nombre] = DatoConEvidencia.model_validate({
            "valor": item["valor"],
            "pagina": item["pagina"],
            "evidencia": item["evidencia"],
        })

    faltantes = [nombre for nombre in CAMPOS_CONTRATO if nombre not in encontrados]
    for nombre in faltantes:
        encontrados[nombre] = DatoConEvidencia(
            valor=None, pagina=None, evidencia=None
        )
    observaciones = list(observaciones) + [
        f"Campo omitido por el modelo: {nombre}" for nombre in faltantes
    ]
    return ExtraccionContrato.model_validate({
        **encontrados,
        "observaciones": observaciones,
    })
