// [F-05] Family relation enum → 中文 label mapping
// Mirrors backend FamilyRelation enum (backend/app/models/family_member.py)

const RELATION_LABELS = {
  self: '本人',
  parent: '父母',
  spouse: '配偶',
  child: '子女',
  sibling: '兄弟姐妹',
  grandparent: '祖父母',
  relative: '亲戚',
  friend: '朋友',
  other: '其他',
}

const RELATION_OPTIONS = [
  { value: 'parent', label: '父母' },
  { value: 'spouse', label: '配偶' },
  { value: 'child', label: '子女' },
  { value: 'sibling', label: '兄弟姐妹' },
  { value: 'grandparent', label: '祖父母' },
  { value: 'relative', label: '亲戚' },
  { value: 'friend', label: '朋友' },
  { value: 'other', label: '其他' },
]

function relationLabel(value) {
  if (!value) return '其他'
  return RELATION_LABELS[value] || '其他'
}

// I18N-DEV-002B: i18n 现算版 (页面渲染时用)。
// key = relation enum 值。未命中回退 relation.other。
var _i18n = require('./i18n')
function relationLabelI18n(value) {
  var v = value || 'other'
  var key = 'relation.' + v
  var text = _i18n.t(key)
  return text === key ? _i18n.t('relation.other') : text
}

// RELATION_OPTIONS 的 i18n label 现算版 (picker range 用)。
function relationOptionsI18n() {
  return RELATION_OPTIONS.map(function (o) {
    return { value: o.value, label: relationLabelI18n(o.value) }
  })
}

module.exports = {
  RELATION_LABELS,
  RELATION_OPTIONS,
  relationLabel,
  relationLabelI18n,
  relationOptionsI18n,
}
