package com.vantuilpjunior.crysenseai.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.concurrent.TimeUnit

@Composable
fun HungerReminderCard(timeSinceFeedMs: Long?, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF3E0)),
        elevation = CardDefaults.cardElevation(2.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                "Lembrete: Amamentação",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFFE65100)
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                "O bebê parece estar com fome! Ofereça o peito ou a mamadeira.",
                style = MaterialTheme.typography.bodyMedium
            )

            if (timeSinceFeedMs != null) {
                val hours = TimeUnit.MILLISECONDS.toHours(timeSinceFeedMs)
                val mins = TimeUnit.MILLISECONDS.toMinutes(timeSinceFeedMs) % 60
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    "Última vez que registramos choro de fome: há $hours horas e $mins minutos.",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.DarkGray,
                    fontWeight = FontWeight.Medium
                )
            }
        }
    }
}
