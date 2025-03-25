import streamlit as st
import fitz  # PyMuPDF
import re
import unicodedata
from io import BytesIO

# =======================
# FUNCIONES AUXILIARES
# =======================

def limpiar_espacios(texto):
    texto = unicodedata.normalize("NFKC", texto)
    texto = texto.replace("\xa0", " ")
    texto = texto.replace("\n", " ")
    texto = texto.replace("\t", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()

def indexar_items(pdf, saltar_primera=True):
    indice = []
    patron = re.compile(r"^(\d{1,3})\.")
    for page_num in range(1 if saltar_primera else 0, len(pdf)):
        page = pdf[page_num]
        bloques = page.get_text("blocks")
        for b in bloques:
            y = b[1]
            texto = b[4].strip()
            if y > 750:
                continue
            if any(p in texto.lower() for p in ["página", "cuadernillo", "número", "prueba"]):
                continue
            if re.match(patron, texto):
                numero = int(re.match(patron, texto).group(1))
                indice.append({
                    "item": numero,
                    "pagina": page_num,
                    "y": y
                })
    return sorted(indice, key=lambda x: x["item"])

def indexar_contextos(pdf, saltar_primera=True):
    contextos = []
    patron = re.compile(r"RESPOND[AE]\s+LAS\s+PREGUNTAS\s+(\d{1,3})\s+A\s+(\d{1,3})", re.IGNORECASE)
    for page_num in range(1 if saltar_primera else 0, len(pdf)):
        page = pdf[page_num]
        bloques = page.get_text("blocks")
        bloques = sorted(bloques, key=lambda b: b[1])
        for b in bloques:
            y = b[1]
            texto_raw = b[4].strip()
            if not texto_raw:
                continue
            texto = limpiar_espacios(texto_raw)
            match = patron.search(texto)
            if match:
                desde = int(match.group(1))
                hasta = int(match.group(2))
                contextos.append({
                    "pagina": page_num,
                    "y": y,
                    "desde": desde,
                    "hasta": hasta,
                    "texto": texto
                })
    return contextos

def recortar_items_con_contexto_streamlit(pdf_bytes, indice_items, contextos, items_deseados, buffer_salida, margen_superior=-10):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    nuevo_pdf = fitz.open()

    items_dict = {item["item"]: item for item in indice_items}

    for item_id in items_deseados:
        if item_id not in items_dict:
            print(f"⚠️ Ítem {item_id} no encontrado.")
            continue

        actual = items_dict[item_id]
        y1 = actual["y"] + margen_superior
        pag_actual = doc[actual["pagina"]]

        siguientes = [item for item in indice_items if item["item"] > item_id]
        mismos = [item for item in siguientes if item["pagina"] == actual["pagina"]]
        y2 = mismos[0]["y"] if mismos else pag_actual.rect.height

        contexto_relevante = None
        for c in contextos:
            if c["desde"] <= item_id <= c["hasta"]:
                contexto_relevante = c
                break

        bloques = []

        if contexto_relevante:
            pag_ctx = doc[contexto_relevante["pagina"]]
            y_ctx1 = contexto_relevante["y"] + margen_superior
            item_inicio = items_dict.get(contexto_relevante["desde"])
            y_ctx2 = item_inicio["y"] if item_inicio and item_inicio["pagina"] == contexto_relevante["pagina"] else pag_ctx.rect.height
            bloques.append({
                "pagina": contexto_relevante["pagina"],
                "y1": y_ctx1,
                "y2": y_ctx2
            })

        bloques.append({
            "pagina": actual["pagina"],
            "y1": y1,
            "y2": y2
        })

        for bloque in bloques:
            pagina = doc[bloque["pagina"]]
            rect = fitz.Rect(0, bloque["y1"], pagina.rect.width, bloque["y2"])
            nueva_pagina = nuevo_pdf.new_page(width=rect.width, height=rect.height)
            nueva_pagina.show_pdf_page(fitz.Rect(0, 0, rect.width, rect.height),
                                       doc, bloque["pagina"], clip=rect)

    nuevo_pdf.save(buffer_salida)
    nuevo_pdf.close()
    doc.close()

# =======================
# INTERFAZ STREAMLIT
# =======================

st.set_page_config(page_title="Recorte de Ítems", page_icon="✂️")
st.title("✂️ Recorte de Ítems con Contexto")

pdf_file = st.file_uploader("📄 Sube el PDF de la prueba", type="pdf")
item_input = st.text_input("🔢 ¿Qué ítems necesitas? (Ejemplo: 3, 7, 15, 22)")

if pdf_file and item_input:
    try:
        items_deseados = [int(i.strip()) for i in item_input.split(",") if i.strip().isdigit()]
        
        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        indice_items = indexar_items(doc)
        contextos = indexar_contextos(doc)
        doc.close()

        st.info(f"🔍 Se detectaron {len(indice_items)} ítems y {len(contextos)} contextos.")

        output_pdf = BytesIO()
        recortar_items_con_contexto_streamlit(pdf_bytes, indice_items, contextos, items_deseados, output_pdf)

        st.success("✅ PDF generado con éxito.")
        st.download_button("📥 Descargar PDF recortado", output_pdf.getvalue(), file_name="recorte_items.pdf")

    except Exception as e:
        st.error(f"❌ Error procesando el archivo: {e}")
