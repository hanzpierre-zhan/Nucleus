"""Script para insertar 50 incidencias ficticias de prueba con historial de bitácora completo"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, Incidencia, HistorialIncidencia, OpcionDesplegable
from datetime import datetime, timedelta
import random

# Listas de opciones reales del sistema
departamentos = ["Lima", "Arequipa", "Cusco", "Piura", "La Libertad", "Junin", "Tacna", "Ica", "Ancash", "Loreto", "Cajamarca"]
contratas = ["Jius", "Gesitel", "HBA Proyect", "Satelecom", "Cobra", "Nastel"]
slas = ["8HRS", "16HRS", "48HRS"]
estados = ["Pendiente", "Asignado", "Parada de Reloj", "Cierre Operativo", "Liquidado"]
proyectos = ["FLM", "PEXT"]
servicios = ["PREVENTIVO", "CORRECTIVO", "PREDICTIVO", "AVAST DE COMBUSTIBLE", "ADICIONALES"]
tecnicos = ["Juan Pérez", "Carlos López", "María García", "Pedro Ramírez", "José Flores", "Ana Mendoza"]
gestores = [
    ("hvargas", "Hector Vargas"),
    ("mgarcia", "Marcos Garcia"),
    ("lrojas", "Luz Rojas"),
    ("jchavez", "Julio Chavez")
]

sitios = [
    "0131601_JU_Huancayo_Centro",
    "0131673_JU_Univ_Continental",
    "013191749_HU_Zenovio_Rodriguez",
    "013192129_HU_Castrovirreyna",
    "0132501_MD_Ernesto_Rivero",
    "0132533_MD_Puerto_Rosario",
    "0132537_MD_Caserio_Sta_Rosa",
    "013295793_CP_Campamento_Yumpaq"
]

descripciones_falla = [
    "Corte de energía comercial en el nodo principal de transmisión. Sitio operando con baterías.",
    "Radioenlace microondas presenta alta tasa de error de bits (BER) por desalineamiento de antena.",
    "Falla en tarjeta controladora de OLT GPON afectando a clientes corporativos.",
    "Intento de vandalismo en acometida eléctrica externa del gabinete de exteriores.",
    "Alarmas de alta temperatura en gabinete de shelter por falla en equipo de aire acondicionado.",
    "Bajo nivel de combustible en grupo electrógeno. Requiere recarga de emergencia urgente.",
    "Atenuación de fibra óptica por curvatura o daño de cable aéreo en tramo de acceso.",
    "Pérdida total de gestión en router de frontera. Posible daño por sobretensión."
]

comentarios_fase = {
    "Pendiente": [
        "Ticket creado de forma automática tras alarma del NMS.",
        "Se reporta afectación de cobertura en la zona por caída de portadoras.",
        "Incidente escalado por el área de monitoreo para atención urgente."
    ],
    "Asignado": [
        "Se asigna a contrata con instrucciones de validar fusibles y energía.",
        "Técnico en camino portando repuesto de módulo óptico SFP y herramientas.",
        "Desplazamiento autorizado para revisión en sitio física del radioenlace."
    ],
    "Parada de Reloj": [
        "Reloj detenido por restricción de acceso nocturno de la comunidad.",
        "Reloj parado en espera de que la contrata de energía termine trabajos de media tensión.",
        "En espera de repuesto especializado en almacén central."
    ],
    "Cierre Operativo": [
        "Trabajos concluidos. Enlace levantado y alarmas normalizadas.",
        "Reemplazo de fuente de alimentación defectuosa completado. Sitio en servicio.",
        "Se realiza limpieza del filtro de aire y reseteo del equipo de clima. Alarmas despejadas."
    ],
    "Liquidado": [
        "Validado con cliente y NMS durante 24 horas. Servicio estable, ticket liquidado.",
        "Documentación y fotos de entrega aprobadas por el supervisor de zona. Cierre formal.",
        "Monto final aprobado por el cliente. Liquidación de ticket exitosa."
    ]
}

with app.app_context():
    print("Limpiando incidencias y bitacoras anteriores...")
    db.session.query(HistorialIncidencia).delete()
    db.session.query(Incidencia).delete()
    db.session.commit()

    print("Insertando 50 incidencias simuladas con sus historiales...")
    
    # Asegurarnos de que existan opciones mínimas
    for s in sitios:
        if OpcionDesplegable.query.filter_by(categoria='Site Name', valor=s).count() == 0:
            db.session.add(OpcionDesplegable(categoria='Site Name', valor=s))
    db.session.commit()

    base_time = datetime.utcnow() - timedelta(days=15)

    for i in range(1, 51):
        ticket_num = f"INC-{1000 + i}"
        dep = random.choice(departamentos)
        proyecto = random.choice(proyectos)
        servicio = random.choice(servicios)
        estado_final = random.choice(estados)
        site = random.choice(sitios)
        desc = random.choice(descripciones_falla)
        contrata = random.choice(contratas)
        tecnico = random.choice(tecnicos)
        sla = random.choice(slas)

        # Montos según servicio
        monto_aprobado = None
        monto_gastado = None
        if servicio in ["CORRECTIVO", "ADICIONALES"]:
            monto_aprobado = round(random.uniform(500, 3000), 2)
            if estado_final in ["Cierre Operativo", "Liquidado"]:
                monto_gastado = round(monto_aprobado * random.uniform(0.85, 1.05), 2)

        # Determinar el flujo de transiciones según el estado final
        flujo_estados = []
        if estado_final == "Pendiente":
            flujo_estados = ["Pendiente"]
        elif estado_final == "Asignado":
            flujo_estados = ["Pendiente", "Asignado"]
        elif estado_final == "Parada de Reloj":
            flujo_estados = ["Pendiente", "Asignado", "Parada de Reloj"]
        elif estado_final == "Cierre Operativo":
            flujo_estados = ["Pendiente", "Asignado", "Cierre Operativo"]
        elif estado_final == "Liquidado":
            flujo_estados = ["Pendiente", "Asignado", "Cierre Operativo", "Liquidado"]

        # Gestor asignado
        gestor_usr, gestor_nom = random.choice(gestores)

        # Crear Incidencia
        fecha_creacion = base_time + timedelta(hours=i * 6)
        
        inc = Incidencia(
            numero_ticket=ticket_num,
            departamento=dep,
            ciudad=dep + " Central",
            site_name=site,
            fecha_ticket=fecha_creacion,
            fecha_captura=fecha_creacion + timedelta(minutes=random.randint(5, 30)),
            descripcion=desc,
            tecnico_asignado=tecnico,
            contrata=contrata,
            gestor=gestor_nom,
            sla=sla,
            estado=estado_final,
            proyecto=proyecto,
            servicio=servicio,
            monto_aprobado=monto_aprobado,
            monto_gastado=monto_gastado,
            usuario_creador=gestor_usr,
            evidencia="https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c" if estado_final in ["Cierre Operativo", "Liquidado"] else None
        )
        db.session.add(inc)
        db.session.flush() # Obtener id

        # Generar bitácoras de historial
        fecha_evento = inc.fecha_captura
        for idx, est in enumerate(flujo_estados):
            comentario = random.choice(comentarios_fase[est])
            
            # En transiciones, poner el tag de cambio de estado
            if idx > 0:
                est_prev = flujo_estados[idx-1]
                comentario = f"[{est_prev} ➔ {est}] {comentario}"
            
            hist = HistorialIncidencia(
                incidencia_id=inc.id,
                fecha=fecha_evento,
                estado=est,
                gestor=gestor_nom,
                comentario=comentario
            )
            db.session.add(hist)
            # El siguiente evento ocurre unas horas después
            fecha_evento = fecha_evento + timedelta(hours=random.randint(2, 24))

    db.session.commit()
    print("Listo: Semillero de 50 registros ficticios completado con exito!")
