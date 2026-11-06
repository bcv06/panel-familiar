# Panel familiar

Página para mis padres con fotos, clima, precios de frutas y verduras, delivery, noticias y cartelera. Todo se actualiza solo.

## Qué se actualiza y cuándo

| Qué | Cuándo | Fuente | Archivo |
|---|---|---|---|
| Precios de 16 frutas y verduras | Lunes, 06:30 | Jumbo, Lider, Santa Isabel, Unimarc, Tottus | `precios.json` |
| Cartelera (ópera, conciertos, teatro) | Todos los días, 07:00 | Teatro Municipal, Puntoticket | `eventos.json` |
| Noticias internacionales | Todos los días, 07:00 | BBC Mundo, DW, France 24, El País | `noticias.json` |
| Clima de Las Condes | Cada hora | Open-Meteo | en vivo |

Si una fuente falla, se conservan sus datos anteriores y la página lo indica.

## Publicar

1. Sube todos los archivos, incluida la carpeta oculta `.github`.
2. **Settings → Pages**: rama `main`, carpeta `/ (root)`.
3. **Settings → Actions → General → Workflow permissions**: "Read and write permissions".
4. En **Actions**, ejecuta una vez cada flujo con **Run workflow** y revisa el registro.

## Cómo se extraen los precios

- **Jumbo y Santa Isabel**: búsqueda por producto; se lee la ficha estándar de productos de la página y el precio por kg de cada tarjeta.
- **Unimarc**: categoría completa de frutas y verduras.
- **Tottus**: búsqueda por producto; datos de la página.
- **Lider**: búsqueda con navegador automático, porque bloquea descargas directas.

En cada tienda se toma el formato fresco más barato por kg (o por unidad), sin precios de tarjetas ni clubes.

## Notas

- GitHub pausa las tareas programadas si el repositorio pasa 60 días sin actividad. Los commits automáticos cuentan como actividad.
- Si un supermercado cambia su sitio, el registro de Actions lo mostrará como "se conservan los anteriores".
