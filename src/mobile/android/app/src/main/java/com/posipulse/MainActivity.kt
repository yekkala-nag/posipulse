package com.posipulse

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

data class MobileArticle(
    val id: String,
    val sourceName: String,
    val canonicalUrl: String,
    val headline: String,
    val category: String,
    val summaryText: String,
    val wordCount: Int,
    val isRtl: Boolean = false
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    background = Color(0xFF0A0D14),
                    surface = Color(0xFF161E2E),
                    primary = Color(0xFF10B981),
                    secondary = Color(0xFF38BDF8)
                )
            ) {
                PosiPulseAndroidApp()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PosiPulseAndroidApp() {
    val context = LocalContext.current
    var selectedLang by remember { mutableStateOf("en") }

    val languages = listOf(
        Triple("en", "English", false),
        Triple("hi", "हिन्दी", false),
        Triple("bn", "বাংলা", false),
        Triple("mr", "मराठी", false),
        Triple("te", "తెలుగు", false),
        Triple("ta", "தமிழ்", false),
        Triple("ur", "اردو", true),
        Triple("gu", "ગુજરાતી", false),
        Triple("kn", "ಕನ್ನಡ", false),
        Triple("or", "ଓଡ଼ିଆ", false),
        Triple("ml", "മലയാളം", false),
        Triple("pa", "ਪੰਜਾਬੀ", false),
        Triple("as", "অসমীয়া", false),
        Triple("ne", "नेपाली", false),
        Triple("mai", "मैथिली", false),
        Triple("gom", "कोंकणी", false)
    )

    fun openPublisherCustomTab(url: String) {
        val cleanUri = Uri.parse(url)
        val customTabsIntent = CustomTabsIntent.Builder()
            .setShowTitle(true)
            .build()
        customTabsIntent.launchUrl(context, cleanUri)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("🌱 PosiPulse", fontWeight = FontWeight.Bold, color = Color.White)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            "शुद्ध समाचार",
                            fontSize = 12.sp,
                            color = Color(0xFF10B981),
                            modifier = Modifier
                                .background(Color(0x2610B981), RoundedCornerShape(4.dp))
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF0A0D14))
            )
        },
        containerColor = Color(0xFF0A0D14)
    ) { padding ->
        Column(modifier = Modifier.padding(padding)) {
            // Language selector row
            LazyRow(
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(languages) { (code, name, isRtl) ->
                    val isSelected = selectedLang == code
                    Surface(
                        onClick = { selectedLang = code },
                        shape = RoundedCornerShape(20.dp),
                        color = if (isSelected) Color(0x2610B981) else Color(0x0DFFFFFF),
                        border = androidx.compose.foundation.BorderStroke(
                            1.dp,
                            if (isSelected) Color(0xFF10B981) else Color(0x1AFFFFFF)
                        )
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = name,
                                fontWeight = FontWeight.Bold,
                                color = if (isSelected) Color(0xFF10B981) else Color.White
                            )
                            if (isRtl) {
                                Spacer(modifier = Modifier.width(4.dp))
                                Text(
                                    "RTL",
                                    fontSize = 9.sp,
                                    color = Color(0xFFF59E0B),
                                    modifier = Modifier
                                        .background(Color(0x33F59E0B), RoundedCornerShape(3.dp))
                                        .padding(horizontal = 3.dp)
                                )
                            }
                        }
                    }
                }
            }

            // Sample feed
            LazyColumn(
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Renders Android article cards
            }
        }
    }
}
