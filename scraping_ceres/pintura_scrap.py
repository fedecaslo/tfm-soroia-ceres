'''
Código para descargar imágenes de dibujo, joyeria, pintura y fotografía antigua del Museo Sorolla desde CER.es.
Se ha respetado la licencia de uso de los datos del museo desde CER.es, usados para un uso privado y académico.
Cualquier uso comercial o redistribución de los datos debe ser autorizado por el museo.
'''
import requests
from bs4 import BeautifulSoup
import os
import json
import time
import random
import os
import requests
import time
import random
from bs4 import BeautifulSoup
import re

def limpiar_nombre(nombre):
    """
    Reemplaza caracteres problemáticos en nombres de archivos y carpetas.
    """
    return re.sub(r'[\\/:"*?<>|]', '_', nombre)  # Reemplaza / \ : * ? " < > | por _

def descargar_imagenes(inventario_id, ficha_soup, headers):
    """
    Descarga las imágenes en alta calidad de un objeto, iterando hasta que detecta una repetición o final de imágenes.
    :param inventario_id: ID del objeto, utilizado para el nombre de la carpeta
    :param ficha_soup: BeautifulSoup con el contenido de la ficha completa
    :param headers: Encabezados HTTP para las solicitudes
    :return: Lista de rutas de las imágenes descargadas
    """
    image_paths = []
    base_url = "https://ceres.mcu.es/pages/"

    # Buscar enlace "Ampliar Imagen" que lleva al visor
    ampliar_link = ficha_soup.find('p', class_='ampliar')
    if ampliar_link:
        ampliar_href = ampliar_link.find('a')['href']
        visor_url = base_url + ampliar_href  # URL del visor de imágenes
        print(f"URL del visor para {inventario_id}: {visor_url}")  # Depuración de la URL
    else:
        print(f"No se encontró el enlace de ampliación para {inventario_id}")
        return image_paths

    # Buscar el mosaico de imágenes
    mosaic_table = ficha_soup.find('table', {'class': 'tablaLPR3', 'summary': 'Mosaico de imágenes'})
    if mosaic_table:
        mosaic_images = mosaic_table.find_all('img', class_='fotoFC')
        total_images = len(mosaic_images)
        print(f"Se encontraron {total_images} imágenes en el mosaico.")  # Depuración de la cantidad de imágenes
    else:
        print("No se encontró el mosaico de imágenes.")
        total_images = 0

    # Inicializar variables
    img_index = 1
    seen_hashes = set()  # Usamos un conjunto para detectar repeticiones
    print(f"Comenzando descarga de imágenes para {inventario_id}...")  # Depuración inicial

    # Si no hay mosaico de imágenes, descargar la imagen principal
    if total_images == 0:
        try:
            # Construcción de URL corregida
            img_url = f"{base_url}Viewer?accion=42&AMuseo=MSMCOLECCION&Ninv={inventario_id}&txt_id_imagen=1&txt_totalImagenes=1&txt_zoom=10"
            print(f"Descargando imagen principal: {img_url}")  # Depuración de la URL de imagen

            img_data = requests.get(img_url, headers=headers, timeout=10, stream=True)

            # Si la solicitud no fue exitosa, detener
            if img_data.status_code != 200:
                print(f"Error al obtener la imagen principal, terminando descarga.")
                return image_paths

            # Verificar si la respuesta es realmente una imagen
            content_type = img_data.headers.get('Content-Type', '')
            if not content_type.startswith('image'):
                print(f"La URL {img_url} no devolvió una imagen. Deteniendo descarga.")
                return image_paths

            # Guardar la imagen
            safe_id = limpiar_nombre(inventario_id)
            carpeta = f"imagenes/{safe_id}"
            os.makedirs(carpeta, exist_ok=True)
            img_name = f"{carpeta}/{safe_id}_{img_index}.jpg"

            with open(img_name, 'wb') as img_file:
                for chunk in img_data.iter_content(1024):
                    img_file.write(chunk)

            image_paths.append(img_name)
            print(f"Imagen descargada: {img_name}")

            # Espera aleatoria para no sobrecargar el servidor
            time.sleep(random.uniform(1, 3))

        except requests.RequestException as e:
            print(f"Error en la descarga de la imagen principal: {e}")

        return image_paths

    # Recorrer las imágenes del mosaico
    while img_index <= total_images:
        img_url = f"{base_url}Viewer?accion=42&AMuseo=MSMCOLECCION&Ninv={inventario_id}&txt_id_imagen={img_index}&txt_zoom=10"
        print(f"Descargando imagen: {img_url}")  # Depuración de la URL de imagen

        try:
            img_data = requests.get(img_url, headers=headers, timeout=10, stream=True)
            
            # Si la solicitud no fue exitosa, detener
            if img_data.status_code != 200:
                print(f"Error al obtener la imagen {img_index}, terminando descarga.")
                break

            # Obtener el hash de los primeros bytes para comparar imágenes
            img_hash = hash(img_data.content[:1024])

            # Si el hash ya fue visto antes, significa que hemos llegado al final
            if img_hash in seen_hashes:
                print(f"Fin del ciclo de imágenes detectado en {img_index - 1}, deteniendo la descarga.")
                break  # Salimos del bucle sin guardar la imagen duplicada
                
            seen_hashes.add(img_hash)

            # Guardar la imagen solo si no es repetida
            safe_id = limpiar_nombre(inventario_id)
            if not os.path.exists(f"imagenes/{safe_id}"):
                os.makedirs(f"imagenes/{safe_id}")
            img_name = f"imagenes/{safe_id}/{safe_id}_{img_index}.jpg"

            with open(img_name, 'wb') as img_file:
                for chunk in img_data.iter_content(1024):
                    img_file.write(chunk)

            image_paths.append(img_name)
            print(f"Imagen descargada: {img_name}")

            # Asegurarse de añadir un pequeño retraso para no sobrecargar el servidor
            time.sleep(random.uniform(1, 3))  # Espera aleatoria entre 1 y 3 segundos

            img_index += 1  # Incrementar el índice para la siguiente imagen

        except requests.RequestException as e:
            print(f"Error en la descarga de {img_url}: {e}")
            break

    print(f"Finalizada la descarga de imágenes para {inventario_id}. Total descargadas: {len(image_paths)}.")
    return image_paths


def procesar_fichas(headers, base_url, output_file):
    """
    Función que procesa todas las fichas en la página principal, descarga las imágenes y guarda toda la información.
    """
    response = requests.get(base_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    #print(soup)
    pagination_info = soup.find('span', class_='navRecursivaMB2, enLinea')  # Navegación de página

    # Extraer el texto de la paginación
    if pagination_info:
        pages_text = pagination_info.get_text(strip=True)
        # Buscar el número total de páginas (ej. "Página 1 de 60")
        total_pages = int(pages_text.split("de")[-1].strip())  # Esto guarda el número después de "de"
        print(f"Total de páginas a recorrer: {total_pages}")
    else:
        print("No se pudo encontrar la información de la paginación.")
        return

    fichas = {}

    # Bucle principal: recorrer las páginas del resultado
    #for page_num in range(1, total_pages + 1):
    for page_num in range(1, total_pages + 1):
        print(f"Recorriendo página {page_num}...")

        # Actualizar el número de página en la URL
        page_url = f"{base_url}&page={page_num}"

        response = requests.get(page_url, headers=headers)
        if response.status_code != 200:
            print(f"Error al obtener la página {page_num}")
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all("div", class_="contenedorImagenLPR1")

        if not results:
            print(f"No se encontraron resultados en la página {page_num}.")
            continue

        print(f"Se encontraron {len(results)} resultados en la página {page_num}.")

        # Procesar los resultados uno a uno
        for result in results:
            ficha_button = result.find("input", class_="boton_detalleMosaico")  # Botón para acceder a la ficha completa de cada resultado

            if ficha_button:
                # Extraer los valores ocultos para hacer la solicitud POST
                ficha_button_name = ficha_button['name']
                id_value = ficha_button_name.replace("btnDetalle_", "").replace("_MSMCOLECCION", "")
                hidden_value = result.find("input", {"name": f"hiddenIdTabla{id_value}MSMCOLECCION"})
                hidden_tipo_value = result.find("input", {"name": f"hiddenTipoTabla{id_value}MSMCOLECCION"})

                if hidden_value and hidden_tipo_value:
                    hidden_value = hidden_value['value']
                    hidden_tipo_value = hidden_tipo_value['value']
                else:
                    print(f"No se encontraron los campos ocultos para el ID {id_value}")

                ficha_payload = {
                    ficha_button_name: "1",  
                    f"hiddenIdTabla{id_value}MSMCOLECCION": hidden_value if hidden_value else '',
                    f"hiddenTipoTabla{id_value}MSMCOLECCION": hidden_tipo_value if hidden_tipo_value else ''
                }

                # POST para obtener la ficha completa del objeto
                ficha_url = "https://ceres.mcu.es/pages/ResultSearch"
                ficha_response = requests.post(ficha_url, data=ficha_payload, headers=headers)

                # Verificar si la respuesta del POST fue correcta
                if ficha_response.status_code != 200:
                    print(f"Error al obtener la ficha para {id_value}")
                    continue

                # Parsear la ficha completa
                ficha_soup = BeautifulSoup(ficha_response.text, 'html.parser')

                objeto = {}
                table = ficha_soup.find('table', {'summary': 'Tabla de detalle'})  # Tabla con la información del objeto

                inventario_id = None  # Inicializamos la variable

                if table:
                    for row in table.find_all('tr'):
                        header = row.find('th')
                        value = row.find('td')
                        if header and value:
                            key = header.get_text(strip=True)
                            val = value.get_text(strip=True)
                            objeto[key] = val  # Diccionario para guardar Campo->Valor (p.e., "Autor":"Joaquín Sorolla")
                            
                            # Si encuentra el campo "Inventario", se usa como clave
                            if key.lower() == "inventario":
                                inventario_id = val

                if not inventario_id:
                    print(f"Advertencia: No se encontró el número de inventario en la ficha {id_value}. Usando ID alternativo.")
                    inventario_id = id_value  # Si no se encuentra, usa el ID anterior

                # Descargar imágenes con el número de inventario correcto
                imagenes_descargadas = descargar_imagenes(inventario_id, ficha_soup, headers)
                objeto["Imagenes"] = imagenes_descargadas  # Añade un campo Imagenes en la ficha con las rutas de las imagenes

                # Guardar en fichas.json con el inventario como clave
                fichas[inventario_id] = objeto
                with open(f"./fichas/{output_file}.json", "w", encoding="utf-8") as json_file:
                    json.dump(fichas, json_file, ensure_ascii=False, indent=4)

                time.sleep(random.uniform(2, 4))

            else:
                print("Botón de Ficha Completa no encontrado.")

    print("Fichas guardadas")


if __name__ == "__main__":
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    #base_url = "https://ceres.mcu.es/pages/SpecialSearch?Museo=MSMCOLECCION&Where=MSM_Coleccion_Pintura" 
    #base_url = "https://ceres.mcu.es/pages/SpecialSearch?Museo=MSMCOLECCION&Where=MSM_COLECCION_Dibujo"    
    #base_url = "https://ceres.mcu.es/pages/SpecialSearch?Museo=MSMCOLECCION&Where=MSM_COLECCION_Joyeria"
    base_url = "https://ceres.mcu.es/pages/SpecialSearch?Museo=MSMCOLECCION&Where=MSM_Coleccion_FotografiaAntigua"
    procesar_fichas(headers, base_url, 'fotografia')

