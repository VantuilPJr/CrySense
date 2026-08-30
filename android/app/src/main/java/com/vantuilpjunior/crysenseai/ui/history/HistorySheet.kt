package com.vantuilpjunior.crysenseai.ui.history

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.vantuilpjunior.crysenseai.data.local.CryEvent
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistorySheet(
    events: List<CryEvent>,
    onDismiss: () -> Unit
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 32.dp, start = 16.dp, end = 16.dp)
        ) {
            Text(
                "Diário do Bebê (Histórico)",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 16.dp)
            )

            if (events.isEmpty()) {
                Text("Nenhum choro registrado ainda no histórico do celular.")
            } else {
                LazyColumn(modifier = Modifier.fillMaxWidth()) {
                    items(events) { event ->
                        val date = Date(event.timestampMs)
                        val formatter = SimpleDateFormat("dd/MM HH:mm:ss", Locale.getDefault())

                        ListItem(
                            headlineContent = { Text(event.tipo, fontWeight = FontWeight.Bold) },
                            supportingContent = { Text("Confiança da IA: ${event.confianca}%") },
                            trailingContent = { Text(formatter.format(date)) }
                        )
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}
