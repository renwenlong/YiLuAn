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
import com.yiluan.core.model.FamilyMemberProfile

/**
 * 家庭成员管理：列表 + 添加 + 删除。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS FamilyMembersView。
 */
@Composable
fun FamilyMembersScreen(
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }

    LaunchedEffect(Unit) { viewModel.loadFamilyMembers() }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Text(text = stringResource(R.string.family_title))

        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.family_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        )
        OutlinedTextField(
            value = phone,
            onValueChange = { phone = it },
            label = { Text(stringResource(R.string.family_phone)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        )
        Button(
            onClick = {
                viewModel.addFamilyMember(name = name, relation = "other", phone = phone)
                name = ""; phone = ""
            },
            enabled = name.isNotBlank() && !state.isMutating,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        ) {
            Text(stringResource(R.string.family_add))
        }

        if (state.error == ProfileErrorKey.INVALID_INPUT) {
            Text(text = stringResource(R.string.profile_err_invalid))
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(top = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(state.familyMembers, key = { it.id }) { m ->
                FamilyRow(m, onDelete = { viewModel.deleteFamilyMember(m.id) })
            }
        }
    }
}

@Composable
private fun FamilyRow(m: FamilyMemberProfile, onDelete: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.padding(end = 8.dp)) {
                Text(text = m.name)
                m.phone?.let { Text(text = it) }
            }
            TextButton(onClick = onDelete) {
                Text(stringResource(R.string.family_delete))
            }
        }
    }
}
