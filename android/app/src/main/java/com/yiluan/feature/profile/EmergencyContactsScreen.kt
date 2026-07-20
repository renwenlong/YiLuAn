package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.EmergencyContact

/**
 * 紧急联系人管理：列表 + 添加 + 删除。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS EmergencyContactsView。
 */
@Composable
fun EmergencyContactsScreen(
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var relationship by remember { mutableStateOf("") }

    LaunchedEffect(Unit) { viewModel.loadEmergencyContacts() }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Text(text = stringResource(R.string.emergency_title))

        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.emergency_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        )
        OutlinedTextField(
            value = phone,
            onValueChange = { phone = it },
            label = { Text(stringResource(R.string.emergency_phone)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        )
        OutlinedTextField(
            value = relationship,
            onValueChange = { relationship = it },
            label = { Text(stringResource(R.string.emergency_relationship)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        )
        Button(
            onClick = {
                viewModel.addEmergencyContact(name = name, phone = phone, relationship = relationship)
                name = ""; phone = ""; relationship = ""
            },
            enabled = name.isNotBlank() && phone.isNotBlank() && !state.isMutating,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        ) {
            Text(stringResource(R.string.emergency_add))
        }

        if (state.error == ProfileErrorKey.INVALID_INPUT) {
            Text(text = stringResource(R.string.profile_err_invalid))
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(top = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(state.emergencyContacts, key = { it.id }) { c ->
                EmergencyRow(c, onDelete = { viewModel.deleteEmergencyContact(c.id) })
            }
        }
    }
}

@Composable
private fun EmergencyRow(c: EmergencyContact, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.padding(end = 8.dp)) {
                Text(text = c.name)
                Text(text = c.phone)
            }
            TextButton(onClick = onDelete) {
                Text(stringResource(R.string.emergency_delete))
            }
        }
    }
}
