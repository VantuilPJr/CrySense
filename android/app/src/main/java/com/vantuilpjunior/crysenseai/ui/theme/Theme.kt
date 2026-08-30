package com.vantuilpjunior.crysenseai.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val LightColorScheme = lightColorScheme(
    primary = PastelBlueMain,
    onPrimary = SoftText,
    secondary = PastelGreen,
    background = BackgroundLight,
    surface = SurfaceWhite,
    onSurface = SoftText
)

@Composable
fun CrySenseAITheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColorScheme,
        typography = Typography,
        content = content
    )
}