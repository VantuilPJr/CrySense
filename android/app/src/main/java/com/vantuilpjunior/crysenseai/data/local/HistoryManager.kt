package com.vantuilpjunior.crysenseai.data.local

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

data class CryEvent(
    val id: String = java.util.UUID.randomUUID().toString(),
    val tipo: String,       // "COLICA", "FOME"
    val confianca: Int,     // 0-100; o servidor já validou o limiar do evento
    val timestampMs: Long   // epoch ms local
)

class HistoryManager(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("crysense_history", Context.MODE_PRIVATE)
    private val gson = Gson()
    private val KEY_HISTORY = "history_events"

    // Retorna todos os eventos salvos (mais recentes primeiro)
    fun getHistory(): List<CryEvent> {
        val json = prefs.getString(KEY_HISTORY, "[]")
        val type = object : TypeToken<List<CryEvent>>() {}.type
        return gson.fromJson(json, type) ?: emptyList()
    }

    // Salva um novo evento (mantendo limite de 100 eventos)
    fun addEvent(event: CryEvent) {
        val current = getHistory().toMutableList()
        // Evita duplicatas exatas no mesmo minuto para não encher o log
        val last = current.firstOrNull()
        if (last != null && last.tipo == event.tipo && (event.timestampMs - last.timestampMs) < 60000) {
            return // Ignora alerta repetido colado
        }

        current.add(0, event) // Adiciona no início
        if (current.size > 100) {
            current.removeAt(current.size - 1)
        }

        prefs.edit().putString(KEY_HISTORY, gson.toJson(current)).apply()
    }

    // Obtém o tempo decorrido desde a última amamentação (última FOME com confiança alta)
    fun getTimeSinceLastFeedMs(): Long? {
        val lastFeed = getHistory().firstOrNull { it.tipo.uppercase() == "FOME" }
        if (lastFeed != null) {
            return System.currentTimeMillis() - lastFeed.timestampMs
        }
        return null
    }
}
