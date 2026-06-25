CREATE TABLE IF NOT EXISTS focus_checkins (
    id                  SERIAL       PRIMARY KEY,
    fecha               DATE         NOT NULL,
    tipo                VARCHAR(10)  NOT NULL CHECK (tipo IN ('manana', 'noche')),
    proyecto_declarado  TEXT,
    resultado           VARCHAR(20)  NOT NULL CHECK (resultado IN ('avance', 'desvio', 'sin_respuesta')),
    detalle             TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (fecha, tipo)
);
