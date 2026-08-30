package com.vantuilpjunior.crysenseai.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun ColicGuidelinesCard(modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFFDEBEA)),
        elevation = CardDefaults.cardElevation(2.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                "Tática dos 5S (Dr. Harvey Karp)",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFFC62828)
            )
            Spacer(modifier = Modifier.height(12.dp))
            Text("1. Swaddle (Charuto): Enrole o bebê firmemente (livre nas pernas).", style = MaterialTheme.typography.bodyMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Text("2. Side/Stomach: Segure-o de lado ou bruços (só enquanto acorda).", style = MaterialTheme.typography.bodyMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Text("3. Shush: Faça 'Shhh' alto igual ao ruído uterino.", style = MaterialTheme.typography.bodyMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Text("4. Swing (Balanço): Balance rítmica e suavemente.", style = MaterialTheme.typography.bodyMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Text("5. Suck (Sucção): Ofereça chupeta, dedo ou o peito.", style = MaterialTheme.typography.bodyMedium)
        }
    }
}
