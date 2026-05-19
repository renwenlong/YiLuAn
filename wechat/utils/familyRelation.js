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

module.exports = {
  RELATION_LABELS,
  RELATION_OPTIONS,
  relationLabel,
}
