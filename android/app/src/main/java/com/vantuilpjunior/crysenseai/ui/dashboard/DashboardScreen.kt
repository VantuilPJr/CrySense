package com.vantuilpjunior.crysenseai.ui.dashboard

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeviceThermostat
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.SignalWifi4Bar
import androidx.compose.material.icons.filled.SignalWifiOff
import androidx.compose.material.icons.filled.History
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantuilpjunior.crysenseai.data.remote.firebase.MonitorState
import com.vantuilpjunior.crysenseai.ui.theme.*
import com.vantuilpjunior.crysenseai.data.local.HistoryManager
import com.vantuilpjunior.crysenseai.ui.components.ColicGuidelinesCard
import com.vantuilpjunior.crysenseai.ui.components.HungerReminderCard
import com.vantuilpjunior.crysenseai.ui.history.HistorySheet

// Paleta de alertas por tipo
private val colorByType: Map<String, Color> = mapOf(
    "COLICA" to Color(0xFFE53935),
    "FOME"   to Color(0xFFFB8C00),
    "SONO"   to Color(0xFF1E88E5)
)

@Composable
fun DashboardScreen(state: MonitorState, historyManager: HistoryManager? = null) {
    var showHistory by remember { mutableStateOf(false) }
    val tipo     = state.status.tipo.uppercase()
    val isAlert  = state.isAlert
    val alertColor = colorByType[tipo] ?: PastelBlueDark

    val bgColor by animateColorAsState(
        targetValue = if (isAlert) alertColor.copy(alpha = 0.08f) else BackgroundLight,
        animationSpec = tween(600),
        label = "bg"
    )

    Scaffold(containerColor = bgColor) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp, vertical = 16.dp)
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // ── Header ──────────────────────────────────────────────
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "CRYSENSE AI",
                    style = MaterialTheme.typography.titleMedium,
                    color = PastelBlueDark,
                    fontWeight = FontWeight.Bold
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OnlineBadge(online = state.online)
                    Spacer(modifier = Modifier.width(8.dp))
                    IconButton(onClick = { showHistory = true }) {
                        Icon(Icons.Default.History, contentDescription = "Histórico", tint = PastelBlueDark)
                    }
                }
            }

            // --- Suporte Inteligente (App Guide) ---
            if (isAlert) {
                if (tipo == "COLICA") {
                    ColicGuidelinesCard()
                } else if (tipo == "FOME") {
                    val ms = historyManager?.getTimeSinceLastFeedMs()
                    HungerReminderCard(timeSinceFeedMs = ms)
                }
            }

            // ── Status Central ───────────────────────────────────────
            StatusCard(state = state, alertColor = alertColor)

            // ── Sensores BME280 ──────────────────────────────────────
            Text(
                "Ambiente",
                style = MaterialTheme.typography.labelMedium,
                color = SoftText,
                modifier = Modifier.fillMaxWidth()
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                SmallSensorCard(
                    label = "Temperatura",
                    value = "%.1f°C".format(state.sensores.temperatura),
                    icon  = Icons.Default.DeviceThermostat,
                    color = if (state.sensores.temperatura in 18f..28f) PastelBlueDark else Color(0xFFE53935),
                    modifier = Modifier.weight(1f)
                )
                SmallSensorCard(
                    label = "Umidade",
                    value = "%.0f%%".format(state.sensores.umidade),
                    icon  = Icons.Default.WaterDrop,
                    color = PastelBlueDark,
                    modifier = Modifier.weight(1f)
                )
                SmallSensorCard(
                    label = "Pressão",
                    value = "%.0f hPa".format(state.sensores.pressao),
                    icon  = Icons.Default.DeviceThermostat,
                    color = Color(0xFF6D4C41),
                    modifier = Modifier.weight(1f)
                )
            }

            // ── Conforto térmico ──────────────────────────────────────
            val confortoOk = state.sensores.temperatura in 18f..28f && state.sensores.umidade < 75f
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                color = if (confortoOk) Color(0xFF1E88E5).copy(alpha = 0.10f) else Color(0xFFE53935).copy(alpha = 0.10f),
            ) {
                Row(
                    modifier = Modifier.padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(if (confortoOk) "✅" else "⚠️", fontSize = 20.sp)
                    Column {
                        Text(
                            if (confortoOk) "Conforto Térmico: Adequado"
                            else            "Conforto Térmico: Inadequado",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = if (confortoOk) PastelBlueDark else Color(0xFFE53935)
                        )
                        Text(
                            "Ideal: 18–28°C, umidade < 75%",
                            style = MaterialTheme.typography.bodySmall,
                            color = SoftText
                        )
                    }
                }
            }

            // ── Sistema (heartbeat) ──────────────────────────────────
            if (state.heartbeat.uptime > 0) {
                Text(
                    "Sistema",
                    style = MaterialTheme.typography.labelMedium,
                    color = SoftText,
                    modifier = Modifier.fillMaxWidth()
                )
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f)
                ) {
                    Row(
                        modifier = Modifier.padding(14.dp),
                        horizontalArrangement = Arrangement.SpaceAround
                    ) {
                        HeartbeatItem("Uptime", state.uptimeLabel)
                        HeartbeatItem("Heap Livre", "${state.heartbeat.heap_livre / 1024} KB")
                        HeartbeatItem("Inferência", "${state.heartbeat.inferencia_ms} ms")
                    }
                }
            }
        }
    }

    if (showHistory && historyManager != null) {
        HistorySheet(events = historyManager.getHistory()) {
            showHistory = false
        }
    }
}

// ── Componentes auxiliares ────────────────────────────────────────────────────

@Composable
fun OnlineBadge(online: Boolean) {
    val pulse = rememberInfiniteTransition(label = "pulse")
    val scale by pulse.animateFloat(
        initialValue = 0.9f, targetValue = 1.1f,
        animationSpec = infiniteRepeatable(tween(800), RepeatMode.Reverse),
        label = "scale"
    )
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Box(
            modifier = Modifier
                .scale(if (online) scale else 1f)
                .size(10.dp)
                .clip(CircleShape)
                .background(if (online) Color(0xFF43A047) else Color(0xFFE53935))
        )
        Text(
            if (online) "Online" else "Offline",
            style = MaterialTheme.typography.bodySmall,
            color = if (online) Color(0xFF43A047) else Color(0xFFE53935)
        )
        Icon(
            imageVector = if (online) Icons.Default.SignalWifi4Bar else Icons.Default.SignalWifiOff,
            contentDescription = null,
            tint = if (online) Color(0xFF43A047) else Color(0xFFE53935),
            modifier = Modifier.size(16.dp)
        )
    }
}

@Composable
fun StatusCard(state: MonitorState, alertColor: Color) {
    val infiniteTransition = rememberInfiniteTransition(label = "alert_pulse")
    val alpha by infiniteTransition.animateFloat(
        initialValue = 0.7f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse),
        label = "alpha"
    )

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .wrapContentHeight(),
        shape = RoundedCornerShape(20.dp),
        color = if (state.isAlert) alertColor.copy(alpha = 0.15f) else PastelBlueMain.copy(alpha = 0.15f),
        tonalElevation = 2.dp
    ) {
        Column(
            modifier = Modifier.padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Emoji grande central
            Text(
                text = when (state.status.tipo.uppercase()) {
                    "COLICA" -> "😭"
                    "FOME"   -> "🍼"
                    "SONO"   -> "😴"
                    else     -> if (state.online) "😊" else "📡"
                },
                fontSize = 64.sp
            )

            // Label principal
            Text(
                text = state.tipoLabel,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.ExtraBold,
                color = if (state.isAlert) alertColor else PastelBlueDark,
                textAlign = TextAlign.Center
            )

            // Sub-texto
            Text(
                text = when {
                    state.isAlert       -> "Confiança: ${state.status.confianca}%"
                    state.online        -> "Monitorando o bebê..."
                    else                -> "Aguardando conexão com o sensor"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = SoftText,
                textAlign = TextAlign.Center
            )

            // Barra de confiança (só em alerta)
            if (state.isAlert) {
                LinearProgressIndicator(
                    progress = { state.status.confianca / 100f },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(6.dp)
                        .clip(RoundedCornerShape(3.dp)),
                    color = alertColor,
                    trackColor = alertColor.copy(alpha = 0.2f)
                )
            }
        }
    }
}

@Composable
fun SmallSensorCard(
    label: String,
    value: String,
    icon: ImageVector,
    color: Color,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        color = color.copy(alpha = 0.08f),
        tonalElevation = 1.dp
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(20.dp))
            Text(value, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = color, textAlign = TextAlign.Center)
            Text(label, fontSize = 10.sp, color = SoftText, textAlign = TextAlign.Center)
        }
    }
}

@Composable
fun HeartbeatItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium, color = PastelBlueDark)
        Text(label, style = MaterialTheme.typography.bodySmall, color = SoftText)
    }
}
