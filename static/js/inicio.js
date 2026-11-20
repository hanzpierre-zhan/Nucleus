(() => {
  const frases = JSON.parse(document.getElementById('inicio-frases').textContent);
  const fecha = document.getElementById('inicio-fecha');
  const texto = document.getElementById('inicio-frase');
  const autor = document.getElementById('inicio-autor');
  const anterior = document.getElementById('inicio-anterior');
  const siguiente = document.getElementById('inicio-siguiente');
  let indice = 0;

  function mostrar() {
    const frase = frases[indice];
    fecha.textContent = frase.fecha + (indice ? ' · Historial' : ' · Mensaje del día');
    texto.textContent = '«' + frase.texto + '»';
    autor.textContent = frase.autor;
    autor.href = frase.fuente;
    anterior.disabled = indice === frases.length - 1;
    siguiente.disabled = indice === 0;
  }

  anterior.onclick = () => { indice++; mostrar(); };
  siguiente.onclick = () => { indice--; mostrar(); };
})();
