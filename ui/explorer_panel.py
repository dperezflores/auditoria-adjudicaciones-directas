"""Pantalla 1 de Fase 1: explorador de obras y documentos con selección segura.

El backend existente continúa en ui.expedientes; este módulo sólo presenta
el inventario y llama a _analyze bajo una acción del usuario. No permite
enviar PDF de otra obra, reintentar un intento bloqueado ni usar Gemini
al abrir la pantalla. Sin credenciales muestra un ejemplo sintético seguro.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Mapping

import pandas as pd
import streamlit as st

from services.analysis_catalog import FileStatus, file_states, folder_states
from services.document_classifier import code_from_filename, XLSX_MIME
from services.drive_service import (
    DocumentRecord, DriveInventory, WorkRecord, is_configured,
)
from services.gemini_service import DEFAULT_MODEL
from services.selection_rules import SelectionPlan, plan_work_selection, MAX_BATCH
from services.sheets_service import storage_configured
from ui.components import barra_seleccion, pildora_estado, icono
from ui.expedientes import (
    ENABLED_EXTRACTORS, _analyze, _refresh_inventory,
    _render_delete_analysis, _summarize_saved,
)
from ui.preview_data import visual_preview
from ui.theme import EXPECTED_DOCUMENTS, OPTIONAL_DOCUMENT


def supported_docs(work: WorkRecord) -> tuple[DocumentRecord, ...]:
    """El mismo universo que file_states/folder_states: PDF y catálogo XLSX."""
    return (
        *work.pdfs,
        *(d for d in work.other_files
          if code_from_filename(d.name, d.mime_type) == "CATALOGO"),
    )


def _full_name(doc: DocumentRecord) -> str:
    return (doc.relative_path + "/" if doc.relative_path else "") + doc.name


def _date_short(value: str) -> str:
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return "—"


def _drive_link(work: WorkRecord, doc: DocumentRecord | None = None) -> str | None:
    """Sólo enlaces HTTPS devueltos por Drive o ID de archivo verificado."""
    import re
    value = doc.url if doc is not None else work.url
    if value and value.startswith("https://drive.google.com/"):
        return value
    identifier = doc.id if doc is not None else work.id
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", identifier):
        if doc is not None:
            return f"https://drive.google.com/file/d/{identifier}/view"
        return f"https://drive.google.com/drive/folders/{identifier}"
    return None


def _state_for(doc: DocumentRecord, states: Mapping[str, FileStatus]) -> str:
    if doc.id in states:
        return states[doc.id].label
    return "POR_IDENTIFICAR" if not code_from_filename(doc.name, doc.mime_type) else "Sin registrar"


def _selection() -> set[str]:
    return set(st.session_state.get("ex_v2_selected_ids") or ())


def _set_selected(work_id: str, identifiers: set[str]) -> None:
    """Callback previo a rerun: nunca cambia el valor de un widget ya renderizado."""
    st.session_state["ex_v2_selected_work"] = work_id
    st.session_state["ex_v2_focus_work"] = work_id
    st.session_state["ex_v2_selected_ids"] = sorted(identifiers)
    # Sincronizar controles persistentes en el callback, antes de que Streamlit
    # los instancie de nuevo. La selección siempre pertenece a UNA obra.
    known_eligible = set(
        st.session_state.get("ex_v2_known_eligible", {}).get(work_id, ())
    )
    for key in tuple(st.session_state.keys()):
        if key.startswith("ex_v2_cb_row_"):
            st.session_state[key] = key[len("ex_v2_cb_row_"):] in identifiers
        elif key.startswith("ex_v2_cb_"):
            st.session_state[key] = key[len("ex_v2_cb_"):] in identifiers
        elif key.startswith("ex_v2_work_cb_"):
            st.session_state[key] = (
                key[len("ex_v2_work_cb_"):] == work_id
                and bool(known_eligible)
                and known_eligible.issubset(identifiers)
            )


def _focus_work(work_id: str) -> None:
    previous = st.session_state.get("ex_v2_focus_work")
    st.session_state["ex_v2_focus_work"] = work_id
    expanded = set(st.session_state.get("ex_v2_expanded") or ())
    expanded.add(work_id)
    st.session_state["ex_v2_expanded"] = sorted(expanded)
    if previous != work_id:
        _set_selected(work_id, set())
        st.session_state.pop("ex_v2_active_doc", None)


def _toggle_expand(work_id: str) -> None:
    expanded = set(st.session_state.get("ex_v2_expanded") or ())
    if work_id in expanded:
        expanded.remove(work_id)
    else:
        expanded.add(work_id)
    st.session_state["ex_v2_expanded"] = sorted(expanded)


def _toggle_document(work_id: str, doc_id: str, eligible_ids: frozenset[str]) -> None:
    if doc_id not in eligible_ids:
        return
    selection = (
        _selection() if st.session_state.get("ex_v2_selected_work") == work_id else set()
    )
    if st.session_state.get(f"ex_v2_cb_{doc_id}", False):
        selection.add(doc_id)
    else:
        selection.discard(doc_id)
    _set_selected(work_id, selection)


def _toggle_work(work_id: str, eligible_ids: frozenset[str]) -> None:
    if st.session_state.get(f"ex_v2_work_cb_{work_id}", False):
        _set_selected(work_id, set(eligible_ids))
    else:
        _set_selected(work_id, set())


def _select_one(work_id: str, doc_id: str) -> None:
    _set_selected(work_id, {doc_id})


def _select_all(work_id: str, eligible_ids: frozenset[str]) -> None:
    _set_selected(work_id, set(eligible_ids))


def _clear_selection() -> None:
    _set_selected(st.session_state.get("ex_v2_selected_work") or "", set())


def _open_document(work_id: str, doc_id: str) -> None:
    _focus_work(work_id)
    st.session_state["ex_v2_active_doc"] = doc_id


def _request_analysis() -> None:
    """Se ejecuta la extracción en el flujo principal tras revalidar elegibilidad."""
    st.session_state["ex_v2_request_analysis"] = True


def _work_summary(folder, *, compact: bool = False) -> str:
    if folder.total == 0:
        return "Sin documentos compatibles"
    if folder.complete == folder.total:
        return "Todo analizado"
    if compact:
        return f"{folder.complete}/{folder.total} analizados · {folder.pending} pendientes"
    return f"{folder.complete} de {folder.total} analizados · {folder.pending} por analizar"


def _folder_has_no_attempt(work: WorkRecord, tables: dict, folder) -> bool:
    if folder.complete or folder.partial:
        return False
    ids = {d.id for d in supported_docs(work)}
    return not any(a.get("documento_id") in ids for a in tables["Extracciones"])


def _load_or_preview() -> tuple[DriveInventory, dict, dict, bool] | None:
    """El modo demostración no consulta APIs ni abre documentos reales."""
    if not is_configured(st.secrets) or not storage_configured(st.secrets):
        inventory, tables, statuses = visual_preview()
        st.info(
            "**Vista previa de diseño — documentos ficticios.** No hay conexión "
            "a Drive ni Google Sheets. Puedes explorar, buscar y seleccionar, "
            "pero se han deshabilitado análisis, exportaciones y enlaces reales."
        )
        return inventory, tables, statuses, True
    if "ex_inventory" not in st.session_state or "ex_status_tables" not in st.session_state:
        try:
            with st.spinner("Cargando expedientes autorizados..."):
                _refresh_inventory()
        except Exception:
            st.error("No se pudo consultar Google Drive y la hoja maestra.")
            return None
    if st.session_state.get("ex_sync_error"):
        st.error(st.session_state["ex_sync_error"])
    inventory = st.session_state["ex_inventory"]
    tables = st.session_state["ex_status_tables"]
    return inventory, tables, file_states(inventory, tables), False


def _render_tree(
    inventory: DriveInventory,
    tables: dict,
    states: dict,
    folders: dict,
    plans: dict[str, SelectionPlan],
    is_demo: bool,
) -> WorkRecord | None:
    works = inventory.works
    st.markdown("### Obras en la carpeta")
    st.caption(
        f"{len(works)} obras · "
        f"{sum(folders[w.id].pending for w in works)} documentos por analizar"
    )
    search = st.text_input(
        "Buscar obra o archivo", key="ex_v2_search",
        placeholder="Nombre, número o PDF...",
        label_visibility="collapsed",
    ).casefold().strip()
    complete = sum(folders[w.id].label == "Analizada" for w in works)
    to_review = len(works) - complete
    labels = {
        "Todas": f"Todas · {len(works)}",
        "Con pendientes": f"Pendientes · {to_review}",
        "Completas": f"Completas · {complete}",
    }
    mode = st.segmented_control(
        "Filtrar expedientes", tuple(labels),
        key="ex_v2_filter", default="Todas",
        format_func=lambda name: labels[name],
        label_visibility="collapsed",
    ) or "Todas"

    visible = [
        w for w in works
        if (
            not search or search in w.name.casefold()
            or any(search in d.name.casefold() for d in (*w.pdfs, *w.other_files))
        )
        and (
            mode == "Todas"
            or (mode == "Completas" and folders[w.id].label == "Analizada")
            or (mode == "Con pendientes" and folders[w.id].total > 0
                and folders[w.id].label != "Analizada")
        )
    ]
    if not visible:
        st.info("No hay obras que coincidan con la búsqueda.")
        return None

    visible_ids = {w.id for w in visible}
    current_id = st.session_state.get("ex_v2_focus_work")
    if current_id not in visible_ids:
        # Si cambiamos de filtro, la selección previa no puede usarse bajo
        # una obra distinta o invisible.
        _focus_work(visible[0].id)
        current_id = visible[0].id

    expanded = set(st.session_state.get("ex_v2_expanded") or ())
    for work in visible:
        folder = folders[work.id]
        plan = plans[work.id]
        count = len(plan.eligible)
        all_selected = (
            st.session_state.get("ex_v2_selected_work") == work.id
            and bool(count) and plan.eligible_ids.issubset(_selection())
        )
        with st.container(border=True, key=f"ex_v2_work_{work.id}"):
            a, b, c = st.columns([0.65, 0.65, 5.3], gap="small",
                                 vertical_alignment="center")
            with a:
                work_key = f"ex_v2_work_cb_{work.id}"
                if work_key not in st.session_state:
                    st.session_state[work_key] = all_selected
                st.checkbox(
                    f"Seleccionar documentos elegibles de {work.name}",
                    key=work_key, label_visibility="collapsed",
                    disabled=not count,
                    on_change=_toggle_work,
                    args=(work.id, plan.eligible_ids),
                )
            with b:
                st.button(
                    "▾" if work.id in expanded else "▸",
                    key=f"ex_v2_expand_{work.id}",
                    help="Desplegar documentos",
                    on_click=_toggle_expand, args=(work.id,),
                )
            with c:
                st.button(
                    f"📁 {work.name}", key=f"ex_v2_focus_{work.id}",
                    help="Abrir expediente", use_container_width=True,
                    type="primary" if work.id == current_id else "tertiary",
                    on_click=_focus_work, args=(work.id,),
                )
            st.caption(_work_summary(folder, compact=True))
            selected_for_work = (
                _selection() if st.session_state.get("ex_v2_selected_work") == work.id
                else set()
            )
            if selected_for_work and not plan.eligible_ids.issubset(selected_for_work):
                st.caption("– Selección parcial")
            if _folder_has_no_attempt(work, tables, folder) and folder.total:
                st.markdown(pildora_estado("Nueva"), unsafe_allow_html=True)

            if work.id not in expanded:
                continue
            with st.container(key=f"ex_v2_tree_{work.id}"):
                for doc in supported_docs(work):
                    decision = plan.decisions[doc.id]
                    left, middle, right = st.columns([0.68, 4.3, 0.9], gap="small",
                                                      vertical_alignment="center")
                    with left:
                        if decision.selectable:
                            key = f"ex_v2_cb_{doc.id}"
                            if key not in st.session_state:
                                st.session_state[key] = doc.id in selected_for_work
                            st.checkbox(
                                f"Seleccionar {doc.name}", key=key,
                                label_visibility="collapsed",
                                on_change=_toggle_document,
                                args=(work.id, doc.id, plan.eligible_ids),
                            )
                        else:
                            st.markdown("·")
                    with middle:
                        st.caption(
                            f"{'└' if doc.relative_path else '·'} "
                            f"{code_from_filename(doc.name, doc.mime_type) or 'SIN TIPO'} "
                            f"· {_full_name(doc)}"
                        )
                    with right:
                        st.markdown(
                            pildora_estado(_state_for(doc, states)),
                            unsafe_allow_html=True,
                        )
                existing = {
                    code_from_filename(d.name, d.mime_type)
                    for d in supported_docs(work)
                }
                for code, label in EXPECTED_DOCUMENTS:
                    if code not in existing:
                        st.caption(f"· {label} · Falta")
    return next((w for w in visible if w.id == current_id), visible[0])


def _expected_cards(work: WorkRecord, states: dict) -> None:
    present: dict[str, list[DocumentRecord]] = {}
    for doc in supported_docs(work):
        code = code_from_filename(doc.name, doc.mime_type)
        if code:
            present.setdefault(code, []).append(doc)
    kinds = list(EXPECTED_DOCUMENTS)
    if OPTIONAL_DOCUMENT[0] in present:
        kinds.append(OPTIONAL_DOCUMENT)

    st.markdown('<div class="aud-eyebrow">EXPEDIENTE</div>', unsafe_allow_html=True)
    # Tres tarjetas por fila; diseño adaptable mediante columnas nativas.
    for start in range(0, len(kinds), 3):
        row = st.columns(3, gap="small")
        for col, (code, label) in zip(row, kinds[start:start + 3]):
            with col:
                with st.container(border=True, key=f"ex_v2_doc_card_{work.id}_{code}"):
                    st.markdown(f"**{label}**")
                    if code in present:
                        docs = present[code]
                        state = _state_for(docs[0], states)
                        if len({ _state_for(d, states) for d in docs}) > 1:
                            state = "Parcial"
                        st.markdown(pildora_estado(state), unsafe_allow_html=True)
                        st.caption(f"{len(docs)} archivo(s)")
                    else:
                        st.markdown(pildora_estado("Falta"), unsafe_allow_html=True)
                        st.caption("No se encontró en la carpeta")
                    if code == OPTIONAL_DOCUMENT[0]:
                        st.caption("Opcional")


def _render_doc_rows(
    work: WorkRecord, states: dict, plan: SelectionPlan, is_demo: bool,
) -> None:
    st.markdown("### Archivos en la carpeta")
    docs = supported_docs(work)
    if not docs and not work.other_files:
        st.info("Esta carpeta no contiene documentos compatibles.")
        return

    header = st.columns([0.42, 1.4, 2.5, 0.65, 1.08, 0.88, 0.97],
                        gap="small", vertical_alignment="center")
    for col, label in zip(
        header, ("", "Documento", "Archivo", "Tamaño", "Estado", "Actualizado", "Acción"),
    ):
        with col:
            st.caption(label)
    st.divider()
    selected = _selection() if st.session_state.get("ex_v2_selected_work") == work.id else set()
    for idx, doc in enumerate(docs):
        decision = plan.decisions[doc.id]
        file_name = _full_name(doc)
        with st.container(key=f"ex_v2_file_{doc.id}"):
            a, b, c, d, e, f, g = st.columns(
                [0.42, 1.4, 2.5, 0.65, 1.08, 0.88, 0.97],
                gap="small", vertical_alignment="center",
            )
            with a:
                if decision.selectable:
                    key = f"ex_v2_cb_row_{doc.id}"
                    if key not in st.session_state:
                        st.session_state[key] = doc.id in selected
                    st.checkbox(
                        f"Incluir {file_name}", key=key,
                        label_visibility="collapsed",
                        on_change=_toggle_doc_row,
                        args=(work.id, doc.id, plan.eligible_ids),
                    )
                else:
                    st.markdown("·")
            with b:
                st.markdown(
                    f'<span class="aud-type">{escape(code_from_filename(doc.name, doc.mime_type) or "SIN TIPO")}</span>',
                    unsafe_allow_html=True,
                )
            with c:
                st.markdown(
                    f'<span class="aud-file-path" title="{escape(file_name, quote=True)}">'
                    f'{escape(file_name)}</span>', unsafe_allow_html=True,
                )
            with d:
                st.caption(f"{doc.size_bytes / 1_000_000:.2f} MB" if doc.size_bytes else "—")
            with e:
                st.markdown(pildora_estado(_state_for(doc, states)), unsafe_allow_html=True)
            with f:
                st.caption(_date_short(doc.modified_time))
            with g:
                if _state_for(doc, states) == "Analizado":
                    st.button(
                        "Ver datos", key=f"ex_v2_view_{doc.id}",
                        on_click=_open_document, args=(work.id, doc.id),
                        use_container_width=True,
                    )
                elif decision.disposition in ("blocked", "needs_sync", "not_registered") or _state_for(doc, states) in ("Revisar error", "Desactualizado", "Parcial"):
                    st.button(
                        "Revisar", key=f"ex_v2_review_{doc.id}",
                        on_click=_open_document, args=(work.id, doc.id),
                        use_container_width=True,
                    )
                elif decision.selectable:
                    st.button(
                        "Analizar", key=f"ex_v2_choose_{doc.id}",
                        on_click=_select_one, args=(work.id, doc.id),
                        use_container_width=True,
                        disabled=is_demo,
                    )
                else:
                    st.caption("Renombrar en Drive")

    other = [doc for doc in work.other_files if doc not in docs]
    if other:
        st.markdown("#### Otros archivos detectados")
        for doc in other:
            name = _full_name(doc)
            st.markdown(
                f'<div class="aud-unrecognized">{icono("file", size=15)} '
                f'<span class="aud-file-path">{escape(name)}</span>'
                f'<span class="aud-secondary"> · Sin extractor compatible</span></div>',
                unsafe_allow_html=True,
            )


def _toggle_doc_row(work_id: str, doc_id: str, eligible_ids: frozenset[str]) -> None:
    """Sincroniza la selección del renglón con la del árbol de la misma obra."""
    key = f"ex_v2_cb_row_{doc_id}"
    current = (
        _selection() if st.session_state.get("ex_v2_selected_work") == work_id else set()
    )
    if doc_id in eligible_ids:
        if st.session_state.get(key, False):
            current.add(doc_id)
        else:
            current.discard(doc_id)
    _set_selected(work_id, current)
    # Esta clave pertenece al widget que disparó el callback; puede actualizarse
    # en el callback, antes de reconstruir la pantalla.
    st.session_state[key] = doc_id in current


def _doc_detail_panel(work: WorkRecord, doc: DocumentRecord, tables: dict,
                      states: dict, plan: SelectionPlan, is_demo: bool) -> None:
    with st.container(border=True, key="ex_v2_document_panel"):
        heading, close = st.columns([5, 1], vertical_alignment="center")
        with heading:
            st.markdown(f"### {escape(doc.name)}")
            st.caption(f"{_full_name(doc)} · Estado: {_state_for(doc, states)}")
        with close:
            if st.button("Cerrar", key="ex_v2_close_doc"):
                st.session_state.pop("ex_v2_active_doc", None)
                st.rerun()

        if is_demo:
            st.info(
                "Documento ficticio de demostración. El visor con datos y "
                "evidencias originales se conectará en el Paso D."
            )
            return
        decision = plan.decisions.get(doc.id)
        if decision and not decision.selectable and decision.disposition not in ("reused",):
            st.warning(decision.explanation)
        status = states.get(doc.id)
        if status:
            _summarize_saved(doc, tables, status)
            _render_delete_analysis(doc, work, tables)
        else:
            st.info("Archivo sin análisis registrado. Renómbralo en Drive si procede.")
        link = _drive_link(work, doc)
        if link:
            st.link_button("Abrir documento en Drive", link)


def _render_right(
    work: WorkRecord, folders: dict, states: dict, plans: dict,
    tables: dict, is_demo: bool,
) -> None:
    plan = plans[work.id]
    folder = folders[work.id]
    st.markdown(
        f'<div class="aud-breadcrumb">Expedientes / '
        f'<span class="aud-mono">{escape(work.name)}</span></div>',
        unsafe_allow_html=True,
    )
    title, link_col, choose_col = st.columns(
        [4.4, 1.3, 2.3], gap="small", vertical_alignment="center",
    )
    with title:
        st.markdown(f"## {escape(work.name)}")
        st.caption(_work_summary(folder))
    with link_col:
        url = None if is_demo else _drive_link(work)
        if url:
            st.link_button("Abrir en Drive", url, use_container_width=True)
    with choose_col:
        if st.button(
            f"✦ Analizar esta obra ({len(plan.eligible)})",
            key="ex_v2_select_all_focused",
            disabled=not plan.eligible or is_demo,
            type="primary", use_container_width=True,
            help="Marca los documentos pendientes; la ejecución se inicia en la barra inferior.",
            on_click=_select_all, args=(work.id, plan.eligible_ids),
        ):
            st.toast("Documentos elegibles seleccionados. Revisa la barra inferior.")

    _expected_cards(work, states)
    st.divider()
    _render_doc_rows(work, states, plan, is_demo)

    if plan.needs_sync or plan.not_registered:
        st.warning(
            f"{len(plan.needs_sync)+len(plan.not_registered)} documento(s) "
            "requieren Actualizar Google Drive antes de analizarse."
        )
    if plan.blocked:
        st.warning(
            f"{len(plan.blocked)} documento(s) tienen una solicitud sin confirmar. "
            "No se reintentarán automáticamente."
        )
    if plan.reused:
        st.caption(
            f"{len(plan.reused)} documento(s) con análisis vigente: "
            "se reutilizan sin consumir Gemini."
        )
    st.markdown(
        '<div class="aud-legend">'
        f'{pildora_estado("Analizado")} {pildora_estado("Pendiente")} '
        f'{pildora_estado("Parcial")} {pildora_estado("Desactualizado")} '
        f'{pildora_estado("Revisar error")}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Analizado indica extracción guardada, no cumplimiento legal. "
        "Los archivos sin extractor deben renombrarse en Drive. "
        "Los intentos incompletos requieren revisión, no reintento automático."
    )
    open_doc_id = st.session_state.get("ex_v2_active_doc")
    open_doc = next((d for d in supported_docs(work) if d.id == open_doc_id), None)
    if open_doc:
        st.divider()
        _doc_detail_panel(work, open_doc, tables, states, plan, is_demo)

    if (
        st.session_state.get("ex_last_run_obra_id") == work.id
        and st.session_state.get("ex_last_run")
        and not is_demo
    ):
        st.markdown("#### Resultado de la última ejecución")
        st.dataframe(
            pd.DataFrame(st.session_state["ex_last_run"]),
            hide_index=True, use_container_width=True,
        )


def render_expedientes(authenticated: bool) -> None:
    """Nueva presentación de expedientes manteniendo _analyze y la seguridad."""
    st.markdown('<div class="aud-page-head">EXPLORADOR DE EXPEDIENTES</div>',
                unsafe_allow_html=True)
    st.title("Expedientes de obra")
    st.caption(
        "Selecciona una obra, revisa sus archivos y prepara únicamente "
        "los documentos pendientes para analizar."
    )
    if not authenticated:
        st.error("Se requiere iniciar sesión con una cuenta autorizada.")
        return

    loaded = _load_or_preview()
    if loaded is None:
        return
    inventory, tables, states, is_demo = loaded
    folders = folder_states(inventory, states)
    registered = {row["documento_id"]: row for row in tables["Documentos"]}
    extractions = {row["cache_key"]: row for row in tables["Extracciones"]}
    all_extractions = tuple(tables["Extracciones"])

    plans = {
        work.id: plan_work_selection(
            work.id, supported_docs(work), registered, extractions, states,
            ENABLED_EXTRACTORS, extraction_rows=all_extractions,
        ) for work in inventory.works
    }
    st.session_state["ex_v2_known_eligible"] = {
        work_id: tuple(plan.eligible_ids) for work_id, plan in plans.items()
    }
    # Limpiar claves asociadas a checkboxes sólo AL PRINCIPIO de un rerun.
    # Hacerlo tras renderizar los checkboxes produce StreamlitAPIException.
    if st.session_state.pop("ex_v2_reset_after_analysis", False):
        _clear_selection()
    total_files = sum(f.total for f in folders.values())
    analysed_files = sum(f.complete for f in folders.values())
    pending_files = sum(f.pending for f in folders.values())
    meta, processed, pending = st.columns(3, gap="small")
    meta.metric("Obras", len(inventory.works))
    processed.metric("Documentos analizados", f"{analysed_files} / {total_files}")
    pending.metric("Pendientes o parciales", pending_files)

    if not inventory.works:
        st.info("Todavía no se han detectado obras en la carpeta autorizada.")
        return

    # No conservar una selección inválida por cambio de inventario/tipo/esquema.
    owner = st.session_state.get("ex_v2_selected_work")
    if owner in plans:
        allowed = plans[owner].eligible_ids
        current = _selection()
        if not current.issubset(allowed):
            _set_selected(owner, current & allowed)
    else:
        st.session_state["ex_v2_selected_ids"] = []

    left, right = st.columns([1.35, 3.65], gap="medium")
    with left:
        focused = _render_tree(inventory, tables, states, folders, plans, is_demo)
    with right:
        if focused:
            _render_right(focused, folders, states, plans, tables, is_demo)
        else:
            st.info("Elige una obra o modifica los filtros para consultar el expediente.")

    owner_id = st.session_state.get("ex_v2_selected_work")
    active_work = next((w for w in inventory.works if w.id == owner_id), None)
    plan = plans.get(owner_id)
    selected_ids = _selection()
    active_docs = (
        [d for d in plan.eligible if d.id in selected_ids]
        if active_work and plan else []
    )
    catalogue_count = sum(d.mime_type == XLSX_MIME for d in active_docs)
    requires_gemini = any(d.mime_type != XLSX_MIME for d in active_docs)
    gemini = st.secrets.get("gemini", {})
    model = gemini.get("model") or DEFAULT_MODEL
    disabled = (
        is_demo or not active_docs
        or (requires_gemini and not gemini.get("api_key"))
    )
    # Un solo expediente por ejecución, como en la aplicación original.
    # La función de la barra no ejecuta IA por sí misma; marca intención.
    st.markdown('<div class="aud-space-for-bar"></div>', unsafe_allow_html=True)
    barra_seleccion(
        cantidad=len(active_docs),
        obras=1 if active_docs else 0,
        tamano_mb=sum(doc.size_bytes for doc in active_docs) / 1_000_000,
        catalogos=catalogue_count,
        al_limpiar=_clear_selection,
        al_analizar=_request_analysis,
        deshabilitado=disabled,
    )
    if active_docs and len(active_docs) > MAX_BATCH:
        st.info(
            f"Hay {len(active_docs)} documentos seleccionados. "
            f"Se procesarán los primeros {MAX_BATCH} en la próxima ejecución; "
            "los restantes quedan para una nueva solicitud."
        )
    if is_demo:
        st.caption(
            "Modo de diseño sin credenciales Drive/Sheets. "
            "Las acciones de análisis y los datos de evidencia están desactivados."
        )

    # Revalidar todo en el script principal antes de invocar el backend.
    if st.session_state.pop("ex_v2_request_analysis", False):
        if disabled or is_demo or not active_work or not plan:
            st.warning("No hay documentos habilitados para esta ejecución.")
            return
        batch = active_docs[:MAX_BATCH]
        if not batch:
            st.warning("No hay documentos pendientes para procesar.")
            return
        st.session_state["ex_last_run"] = _analyze(active_work, batch, model)
        st.session_state["ex_last_run_obra_id"] = active_work.id
        st.session_state["ex_v2_reset_after_analysis"] = True
        st.rerun()
