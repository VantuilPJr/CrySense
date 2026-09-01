package com.vantuilpjunior.crysenseai.data.remote.firebase

import com.google.firebase.database.DataSnapshot
import com.google.firebase.database.DatabaseError
import com.google.firebase.database.FirebaseDatabase
import com.google.firebase.database.ValueEventListener
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.update

// =============================================================================
// Modelo de dados — espelha exatamente o que o ESP32 grava no RTDB
// =============================================================================

// /crySense/status  — alerta de choro ativo
data class CryStatus(
    val tipo: String = "calmo",        // "COLICA", "FOME", "SONO", "calmo"
    val confianca: Int = 0,            // 0-100
    val temperatura: Float = 0f,
    val umidade: Float = 0f,
    val timestamp: Long = 0L,
    val ativo: Boolean = false
)

// /crySense/sensores — leitura periódica do BME280
data class SensorData(
    val temperatura: Float = 0f,       // °C (1 decimal)
    val umidade: Float = 0f,           // %
    val pressao: Float = 0f,           // hPa
    val ts: Long = 0L
)

// /crySense/heartbeat — prova-de-vida do ESP32
data class Heartbeat(
    val uptime: Long = 0L,             // segundos desde boot
    val heap_livre: Long = 0L,         // bytes
    val inferencia_ms: Int = 0,
    val ativo: Boolean = false,
    val ts: Long = 0L
)

// Agregação de todos os dados — exposta para a UI
data class MonitorState(
    val status: CryStatus = CryStatus(),
    val sensores: SensorData = SensorData(),
    val heartbeat: Heartbeat = Heartbeat(),
    val online: Boolean = false          // true se heartbeat recente (< 2 min)
) {
    // Helpers para a UI
    val isAlert: Boolean get() = status.ativo && status.tipo != "calmo"

    val tipoLabel: String get() = when (status.tipo.uppercase()) {
        "COLICA" -> "🤕 Cólica"
        "FOME"   -> "🍼 Fome"
        "SONO"   -> "😴 Sono"
        else     -> if (status.ativo) "Analisando..." else "Bebê tranquilo"
    }

    val uptimeLabel: String get() {
        val s = heartbeat.uptime
        val h = s / 3600; val m = (s % 3600) / 60; val sec = s % 60
        return "%02d:%02d:%02d".format(h, m, sec)
    }
}

// =============================================================================
// Repositório — ouve os 3 paths do RTDB simultaneamente
// =============================================================================
class BabyMonitorRepository {

    private val db = FirebaseDatabase.getInstance(
        "https://crysense-ai-default-rtdb.firebaseio.com"
    )

    // Paths espelhados do firebase_manager.h do ESP32
    private val statusRef    = db.getReference("crySense/status")
    private val sensoresRef  = db.getReference("crySense/sensores")
    private val heartbeatRef = db.getReference("crySense/heartbeat")

    fun observeMonitor(): Flow<MonitorState> = callbackFlow {

        // Estado compartilhado mutable — cada listener atualiza sua parte
        val state = MutableStateFlow(MonitorState())

        fun emit() = trySend(state.value)

        // --- Listener: /crySense/status ---
        val statusListener = object : ValueEventListener {
            override fun onDataChange(snap: DataSnapshot) {
                val s = CryStatus(
                    tipo       = snap.child("tipo").getValue(String::class.java) ?: "calmo",
                    confianca  = snap.child("confianca").getValue(Int::class.java) ?: 0,
                    temperatura= snap.child("temperatura").getValue(Double::class.java)?.toFloat() ?: 0f,
                    umidade    = snap.child("umidade").getValue(Double::class.java)?.toFloat() ?: 0f,
                    timestamp  = snap.child("timestamp").getValue(Long::class.java) ?: 0L,
                    ativo      = snap.child("ativo").getValue(Boolean::class.java) ?: false
                )
                state.update { it.copy(status = s) }
                emit()
            }
            override fun onCancelled(e: DatabaseError) {}
        }

        // --- Listener: /crySense/sensores ---
        val sensoresListener = object : ValueEventListener {
            override fun onDataChange(snap: DataSnapshot) {
                val s = SensorData(
                    temperatura = snap.child("temperatura").getValue(Double::class.java)?.toFloat() ?: 0f,
                    umidade     = snap.child("umidade").getValue(Double::class.java)?.toFloat() ?: 0f,
                    pressao     = snap.child("pressao").getValue(Double::class.java)?.toFloat() ?: 0f,
                    ts          = snap.child("ts").getValue(Long::class.java) ?: 0L
                )
                state.update { it.copy(sensores = s) }
                emit()
            }
            override fun onCancelled(e: DatabaseError) {}
        }

        // --- Listener: /crySense/heartbeat ---
        val heartbeatListener = object : ValueEventListener {
            override fun onDataChange(snap: DataSnapshot) {
                val h = Heartbeat(
                    uptime       = snap.child("uptime").getValue(Long::class.java) ?: 0L,
                    heap_livre   = snap.child("heap_livre").getValue(Long::class.java) ?: 0L,
                    inferencia_ms= snap.child("inferencia_ms").getValue(Int::class.java) ?: 0,
                    ativo        = snap.child("ativo").getValue(Boolean::class.java) ?: false,
                    ts           = snap.child("ts").getValue(Long::class.java) ?: 0L
                )
                // Online se heartbeat chegou nos últimos 120s (relativo ao uptime)
                val online = h.ativo
                state.update { it.copy(heartbeat = h, online = online) }
                emit()
            }
            override fun onCancelled(e: DatabaseError) {}
        }

        // Registra os 3 listeners
        statusRef.addValueEventListener(statusListener)
        sensoresRef.addValueEventListener(sensoresListener)
        heartbeatRef.addValueEventListener(heartbeatListener)

        // Limpeza ao cancelar o flow
        awaitClose {
            statusRef.removeEventListener(statusListener)
            sensoresRef.removeEventListener(sensoresListener)
            heartbeatRef.removeEventListener(heartbeatListener)
        }
    }
}