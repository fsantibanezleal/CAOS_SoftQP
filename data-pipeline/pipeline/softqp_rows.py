"""Original row units and policy for correct interpretation of violation charts."""


def rows_for(case):
    if case.problem is not None:
        count = case.problem.A.shape[0]
        soft = case.problem.penalty.soft
    else:
        from softqp.reference import NONE

        count = case.reference[2].shape[0]
        soft = case.reference[-1].type != NONE
    items = []

    def add(en, es, unit):
        i = len(items)
        items.append(dict(id=f"r{i:04}", label=dict(en=en, es=es), unit=unit, soft=bool(soft[i])))

    if case.id in ("C09", "C10", "C12"):
        for k in range(20):
            add(f"Acceleration, step {k}", f"Aceleración, paso {k}", "m/s²")
        for k in range(20):
            add(f"Position, step {k + 1}", f"Posición, paso {k + 1}", "m")
            add(f"Velocity, step {k + 1}", f"Velocidad, paso {k + 1}", "m/s")
    elif case.id in ("C13", "C14", "C15"):
        for i, unit in enumerate(["°C", "°C", "kWh"]):
            add(f"Initial state {i}", f"Estado inicial {i}", unit)
        for k in range(96):
            for state, unit in enumerate(["°C", "°C", "kWh"]):
                add(f"Dynamics {state}, step {k}", f"Dinámica {state}, paso {k}", unit)
        for en, es, unit, n in [
            ("Power balance", "Balance de potencia", "kW", 96),
            ("HVAC power", "Potencia HVAC", "kW", 96),
            ("Battery power", "Potencia de batería", "kW", 96),
            ("Grid feeder", "Alimentador", "kW", 96),
            ("Battery capacity", "Capacidad de batería", "kWh", 97),
            ("Terminal charge", "Carga terminal", "kWh", 1),
            ("Comfort", "Confort", "°C", 194),
            ("Grid contract", "Contrato de red", "kW", 96),
            ("Battery health", "Salud de batería", "kWh", 97),
            ("HVAC ramp", "Rampa HVAC", "kW/h", 95),
        ]:
            for k in range(n):
                add(f"{en}, row {k}", f"{es}, fila {k}", unit)
    else:
        for i in range(count):
            add(f"Normalized row {i}", f"Fila normalizada {i}", "1")
    if len(items) != count:
        raise ValueError(f"{case.id}: row metadata count does not match A")
    return items
