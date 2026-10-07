/*
 * Ayudas del formulario de registro de pacientes.
 * Todo es opcional: sin JavaScript el formulario funciona igual y el servidor valida todo.
 */
(function () {
  "use strict";

  var MAYORIA_DE_EDAD = 18;

  // ---------------------------------------------------------------------
  // 1. Departamento -> municipio -> distrito (selects en cascada)
  // ---------------------------------------------------------------------
  function filtrarOpciones(select, idPadre) {
    Array.prototype.forEach.call(select.options, function (opcion) {
      if (!opcion.value) return; // la opción "Seleccione…" siempre queda
      var coincide = Boolean(idPadre) && opcion.getAttribute("data-padre") === idPadre;
      opcion.hidden = !coincide;
      opcion.disabled = !coincide;
    });
    var elegida = select.options[select.selectedIndex];
    if (elegida && elegida.disabled) select.value = "";
    select.disabled = !idPadre;
  }

  document.querySelectorAll("[data-cascada]").forEach(function (grupo) {
    var departamento = grupo.querySelector("[data-nivel='departamento']");
    var municipio = grupo.querySelector("[data-nivel='municipio']");
    var distrito = grupo.querySelector("[data-nivel='distrito']");
    if (!departamento || !municipio || !distrito) return;

    // Si ya hay un distrito elegido (al editar o tras un error), completar los niveles de arriba
    var opcionDistrito = distrito.options[distrito.selectedIndex];
    if (opcionDistrito && opcionDistrito.value) {
      municipio.value = opcionDistrito.getAttribute("data-padre");
      var opcionMunicipio = municipio.options[municipio.selectedIndex];
      if (opcionMunicipio && opcionMunicipio.value) {
        departamento.value = opcionMunicipio.getAttribute("data-padre");
      }
    }
    filtrarOpciones(municipio, departamento.value);
    filtrarOpciones(distrito, municipio.value);

    departamento.addEventListener("change", function () {
      municipio.value = "";
      distrito.value = "";
      filtrarOpciones(municipio, departamento.value);
      filtrarOpciones(distrito, "");
    });
    municipio.addEventListener("change", function () {
      distrito.value = "";
      filtrarOpciones(distrito, municipio.value);
    });
  });

  // ---------------------------------------------------------------------
  // 2. Nacionalidad: país de origen solo para extranjeros
  // ---------------------------------------------------------------------
  var nacionalidad = document.getElementById("id_nacionalidad");
  var bloquePais = document.querySelector("[data-bloque='pais-origen']");
  var bloqueNacimiento = document.querySelector("[data-bloque='nacimiento-sv']");

  function actualizarNacionalidad() {
    if (!nacionalidad) return;
    var extranjero = nacionalidad.value === "EX";
    if (bloquePais) bloquePais.hidden = !extranjero;
    if (bloqueNacimiento) bloqueNacimiento.hidden = extranjero;
  }

  if (nacionalidad) {
    nacionalidad.addEventListener("change", actualizarNacionalidad);
    actualizarNacionalidad();
  }

  // ---------------------------------------------------------------------
  // 3. Edad calculada y responsable obligatorio para menores
  // ---------------------------------------------------------------------
  var fechaNacimiento = document.getElementById("id_fecha_nacimiento");
  var textoEdad = document.getElementById("edad-calculada");

  function describirEdad(valor) {
    if (!valor) return null;
    var partes = valor.split("-").map(Number);
    var nacimiento = new Date(partes[0], partes[1] - 1, partes[2]);
    var hoy = new Date();
    if (isNaN(nacimiento.getTime()) || nacimiento > hoy) return null;
    var meses = (hoy.getFullYear() - nacimiento.getFullYear()) * 12 + (hoy.getMonth() - nacimiento.getMonth());
    if (hoy.getDate() < nacimiento.getDate()) meses -= 1;
    var anios = Math.floor(meses / 12);
    var texto;
    if (meses < 1) {
      var dias = Math.round((hoy - nacimiento) / 86400000);
      texto = dias === 1 ? "1 día" : dias + " días";
    } else if (meses < 24) {
      var resto = meses % 12;
      var textoMeses = resto === 1 ? "1 mes" : resto + " meses";
      texto = anios === 0 ? textoMeses : resto === 0 ? "1 año" : "1 año " + textoMeses;
    } else {
      texto = anios + " años";
    }
    return { anios: anios, texto: texto };
  }

  function actualizarEdad() {
    if (!fechaNacimiento) return;
    var edad = describirEdad(fechaNacimiento.value);
    var esMenor = edad !== null && edad.anios < MAYORIA_DE_EDAD;
    if (textoEdad) {
      textoEdad.textContent = edad ? "Edad: " + edad.texto + (esMenor ? " (menor de edad)" : "") : "";
    }
    document.querySelectorAll("[data-solo-menores]").forEach(function (marca) {
      marca.hidden = !esMenor;
    });
  }

  if (fechaNacimiento) {
    fechaNacimiento.addEventListener("change", actualizarEdad);
    fechaNacimiento.addEventListener("input", actualizarEdad);
    actualizarEdad();
  }

  // ---------------------------------------------------------------------
  // 4. Tipo de documento: ejemplo del formato y campo vacío si no presenta
  // ---------------------------------------------------------------------
  var tipoDocumento = document.getElementById("id_tipo_documento");
  var numeroDocumento = document.getElementById("id_numero_documento");
  var ejemplos = {
    DUI: "00000000-0",
    NUI: "Número Único de Identidad",
    CUN: "Código Único de Nacimiento",
    PARTIDA: "Número de partida",
    MINORIDAD: "Número del carné",
    PASAPORTE: "Número de pasaporte",
    RESIDENTE: "Número del carné de residente",
    NINGUNO: "No aplica",
  };

  function actualizarDocumento() {
    if (!tipoDocumento || !numeroDocumento) return;
    numeroDocumento.placeholder = ejemplos[tipoDocumento.value] || "";
    var sinDocumento = tipoDocumento.value === "NINGUNO";
    if (sinDocumento) numeroDocumento.value = "";
    numeroDocumento.readOnly = sinDocumento;
  }

  if (tipoDocumento) {
    tipoDocumento.addEventListener("change", actualizarDocumento);
    actualizarDocumento();
  }

  // ---------------------------------------------------------------------
  // 5. Dar formato al DUI (00000000-0) y teléfonos (0000-0000) al salir del campo
  // ---------------------------------------------------------------------
  function formatearDui(campo) {
    var digitos = campo.value.replace(/\D/g, "");
    if (digitos.length === 9) campo.value = digitos.slice(0, 8) + "-" + digitos.slice(8);
  }

  function formatearTelefono(campo) {
    var digitos = campo.value.replace(/\D/g, "");
    if (digitos.length === 11 && digitos.indexOf("503") === 0) digitos = digitos.slice(3);
    if (digitos.length === 8) campo.value = digitos.slice(0, 4) + "-" + digitos.slice(4);
  }

  document.querySelectorAll("[data-formato='telefono']").forEach(function (campo) {
    campo.addEventListener("blur", function () { formatearTelefono(campo); });
  });
  document.querySelectorAll("[data-formato='dui']").forEach(function (campo) {
    campo.addEventListener("blur", function () { formatearDui(campo); });
  });
  if (numeroDocumento) {
    numeroDocumento.addEventListener("blur", function () {
      if (tipoDocumento && tipoDocumento.value === "DUI") formatearDui(numeroDocumento);
    });
  }

  // ---------------------------------------------------------------------
  // 6. Asistente paso a paso (solo al registrar): un dato a la vez,
  //    con Anterior / Siguiente y un resumen final antes de guardar.
  // ---------------------------------------------------------------------
  var formulario = document.querySelector("form[data-asistente]");
  var asistente = document.getElementById("asistente");
  if (formulario && asistente) iniciarAsistente(formulario, asistente);

  function iniciarAsistente(formulario, asistente) {
    var lugar = document.getElementById("asistente-campo");
    var textoSeccion = document.getElementById("asistente-seccion");
    var textoProgreso = document.getElementById("asistente-progreso");
    var barra = document.getElementById("asistente-barra");
    var opcional = document.getElementById("asistente-opcional");
    var aviso = document.getElementById("asistente-aviso");
    var resumen = document.getElementById("asistente-resumen");
    var listaResumen = document.getElementById("asistente-resumen-lista");
    var botonAtras = document.getElementById("asistente-atras");
    var botonSiguiente = document.getElementById("asistente-siguiente");
    var botonGuardar = document.getElementById("asistente-guardar");
    var botonCompleto = document.getElementById("asistente-completo");
    var secciones = formulario.querySelectorAll("section");
    var acciones = formulario.querySelector("[data-acciones]");

    // Cada paso recuerda su lugar original para poder devolverlo al formulario
    var pasos = Array.prototype.filter.call(formulario.querySelectorAll("[data-paso]"), function (el) {
      return !el.parentElement.closest("[data-paso]");
    }).map(function (el) {
      var seccion = el.closest("section");
      var titulo = seccion ? seccion.querySelector("h2") : null;
      var marcador = document.createComment("paso");
      el.parentNode.insertBefore(marcador, el);
      return {
        el: el,
        marcador: marcador,
        seccion: titulo ? titulo.textContent.replace(/^\s*\d+\.?\s*/, "").trim() : "",
        esSeccion: el.tagName === "SECTION",
      };
    });

    var actual = null; // paso en pantalla (null = resumen)
    var activo = true;

    function controles(paso) {
      return Array.prototype.slice.call(
        paso.el.querySelectorAll("input:not([type='hidden']), select, textarea")
      );
    }

    function esVisible(paso) {
      if (paso.el.hidden && !paso.esSeccion) return false;
      var lista = controles(paso);
      return lista.length > 0 && lista.some(function (c) { return !c.readOnly; });
    }

    function visibles() { return pasos.filter(esVisible); }

    function obligatorioParaMenor(paso) {
      return Boolean(paso.el.querySelector("[data-solo-menores]:not([hidden])"));
    }

    // Datos obligatorios según lo que se eligió antes (el servidor valida lo mismo)
    function requeridoPorContexto(control) {
      var tipo = tipoDocumento ? tipoDocumento.value : "";
      if (control.name === "numero_documento") return tipo !== "NINGUNO";
      if (control.name === "observaciones") return tipo === "NINGUNO";
      if (control.name === "pais_origen") return Boolean(nacionalidad) && nacionalidad.value === "EX";
      // Solo aparece cuando hay pacientes con el mismo nombre y fecha de nacimiento
      if (control.name === "confirmar_no_duplicado") return true;
      return false;
    }

    function esRequerido(control) {
      // data-obligatorio lo pone el servidor (por ejemplo «Tipo de documento», que ya trae DUI elegido)
      return control.required || requeridoPorContexto(control) || Boolean(control.closest("[data-obligatorio]"));
    }

    function esObligatorio(paso) {
      return obligatorioParaMenor(paso) || controles(paso).some(esRequerido);
    }

    function faltantes(paso) {
      var menor = obligatorioParaMenor(paso);
      return controles(paso).filter(function (c) {
        if (c.readOnly || !(esRequerido(c) || menor)) return false;
        if (c.disabled) return true; // p. ej. distrito sin haber elegido municipio
        return c.type === "checkbox" ? !c.checked : !c.value.trim();
      });
    }

    function devolver(paso) {
      if (!paso) return;
      paso.marcador.parentNode.insertBefore(paso.el, paso.marcador.nextSibling);
      if (paso.esSeccion && activo) paso.el.hidden = true;
    }

    function enfocar(paso) {
      var primero = controles(paso).filter(function (c) { return !c.disabled && !c.readOnly; })[0];
      if (primero) primero.focus();
    }

    function mostrarPaso(paso) {
      devolver(actual);
      actual = paso;
      var lista = visibles();
      var posicion = lista.indexOf(paso);
      lugar.appendChild(paso.el);
      paso.el.hidden = false;
      lugar.hidden = false;
      resumen.hidden = true;
      aviso.hidden = true;
      opcional.hidden = esObligatorio(paso);
      textoSeccion.textContent = paso.seccion;
      textoProgreso.textContent = "Dato " + (posicion + 1) + " de " + lista.length;
      barra.style.width = Math.round((posicion / lista.length) * 100) + "%";
      botonAtras.disabled = posicion <= 0;
      botonSiguiente.hidden = false;
      botonGuardar.hidden = true;
      enfocar(paso);
    }

    function siguiente() {
      if (!actual) return;
      var falta = faltantes(actual);
      if (falta.length) {
        aviso.textContent = obligatorioParaMenor(actual)
          ? "Este dato es obligatorio porque el paciente es menor de 18 años."
          : "Este dato es obligatorio.";
        aviso.hidden = false;
        if (!falta[0].disabled) falta[0].focus();
        return;
      }
      var lista = visibles();
      var posicion = lista.indexOf(actual);
      if (posicion + 1 < lista.length) mostrarPaso(lista[posicion + 1]);
      else mostrarResumen();
    }

    function anterior() {
      var lista = visibles();
      if (!actual) {
        mostrarPaso(lista[lista.length - 1]);
        return;
      }
      var posicion = lista.indexOf(actual);
      if (posicion > 0) mostrarPaso(lista[posicion - 1]);
    }

    function etiquetaDe(control, paso) {
      var etiqueta = control.id ? formulario.querySelector("label[for='" + control.id + "']") : null;
      var texto = etiqueta ? etiqueta.textContent : paso.el.getAttribute("data-etiqueta") || "";
      return texto.replace(/\*/g, "").replace(/\s+/g, " ").trim();
    }

    function valorDe(control) {
      if (control.type === "checkbox") return control.checked ? "Sí" : "No";
      if (control.tagName === "SELECT") {
        return control.value ? control.options[control.selectedIndex].text : "";
      }
      return control.value.trim();
    }

    function mostrarResumen() {
      devolver(actual);
      actual = null;
      lugar.hidden = true;
      opcional.hidden = true;
      aviso.hidden = true;
      resumen.hidden = false;
      textoSeccion.textContent = "Último paso";
      textoProgreso.textContent = "Resumen";
      barra.style.width = "100%";
      botonAtras.disabled = false;
      botonSiguiente.hidden = true;
      botonGuardar.hidden = false;

      listaResumen.textContent = "";
      var grupoActual = null;
      var lista = null;
      visibles().forEach(function (paso) {
        if (paso.seccion !== grupoActual) {
          grupoActual = paso.seccion;
          var titulo = document.createElement("h3");
          titulo.className = "text-sm font-bold uppercase tracking-wide text-verde-teal-oscuro";
          titulo.textContent = paso.seccion;
          lista = document.createElement("dl");
          lista.className = "mt-2 divide-y divide-slate-100 rounded-xl border border-slate-200";
          var bloque = document.createElement("div");
          bloque.appendChild(titulo);
          bloque.appendChild(lista);
          listaResumen.appendChild(bloque);
        }
        controles(paso).forEach(function (control) {
          var fila = document.createElement("div");
          fila.className = "flex items-start justify-between gap-3 px-3 py-2";
          var texto = document.createElement("div");
          var dt = document.createElement("dt");
          dt.className = "text-xs text-slate-500";
          dt.textContent = etiquetaDe(control, paso);
          var dd = document.createElement("dd");
          var valor = valorDe(control);
          dd.className = valor ? "font-medium text-gris-oscuro" : "italic text-slate-400";
          dd.textContent = valor || "(en blanco)";
          texto.appendChild(dt);
          texto.appendChild(dd);
          var corregir = document.createElement("button");
          corregir.type = "button";
          corregir.className = "enlace shrink-0 cursor-pointer text-sm underline";
          corregir.textContent = "Corregir";
          corregir.addEventListener("click", function () { mostrarPaso(paso); });
          fila.appendChild(texto);
          fila.appendChild(corregir);
          lista.appendChild(fila);
        });
      });
      botonGuardar.focus();
    }

    function verFormularioCompleto() {
      activo = false;
      devolver(actual);
      actual = null;
      asistente.hidden = true;
      Array.prototype.forEach.call(secciones, function (s) { s.hidden = false; });
      if (acciones) acciones.hidden = false;
    }

    botonSiguiente.addEventListener("click", siguiente);
    botonAtras.addEventListener("click", anterior);
    botonCompleto.addEventListener("click", verFormularioCompleto);

    // Enter pasa al siguiente dato (en los cuadros de texto largos sigue siendo salto de línea)
    formulario.addEventListener("keydown", function (evento) {
      if (!activo || !actual || evento.key !== "Enter") return;
      var destino = evento.target;
      if (destino.tagName === "TEXTAREA" || destino.tagName === "BUTTON" || destino.tagName === "A") return;
      evento.preventDefault();
      siguiente();
    });

    // Arranque: ocultar el formulario largo y mostrar el primer dato
    // (o el primero con error, si el servidor devolvió errores)
    Array.prototype.forEach.call(secciones, function (s) { s.hidden = true; });
    if (acciones) acciones.hidden = true;
    asistente.hidden = false;
    var lista = visibles();
    var conError = lista.filter(function (paso) {
      return paso.el.querySelector("[aria-invalid='true']") || paso.el.querySelector(".text-red-700");
    })[0];
    if (lista.length) mostrarPaso(conError || lista[0]);
    if (conError) {
      aviso.textContent = "Corrija este dato. Los demás datos que escribió se conservan.";
      aviso.hidden = false;
    }
  }
})();
