"""
Generate the SQL body (orders + chats + notifications + payments + reviews)
for YiLuAn seed.sql.  Outputs to stdout.
"""
import sys

# UUID helpers
def oid(n): return f"c0000001-0000-0000-0000-{n:012d}"
def cid(n): return f"g0000001-0000-0000-0000-{n:012d}"  # chat msgs
def nid(n): return f"n0000001-0000-0000-0000-{n:012d}"
def pid(n): return f"p0000001-0000-0000-0000-{n:012d}"
def rid(n): return f"f0000001-0000-0000-0000-{n:012d}"
def hid(n): return f"h0000001-0000-0000-0000-{n:012d}"  # status history

# Patient user ids (b0000001-0000-0000-0000-00000000000X)  X in 1..10
P = [f"b0000001-0000-0000-0000-{i:012d}" for i in range(1, 11)]
# Companion user ids (b0000002-...)  1..15
C = [f"b0000002-0000-0000-0000-{i:012d}" for i in range(1, 16)]
# Hospital ids
H_BJ = [f"a0000001-0000-0000-0000-{i:012d}" for i in range(1, 9)]
H_SH = [f"a0000001-0000-0000-0000-{i:012d}" for i in range(101, 106)]
H_GZ = [f"a0000001-0000-0000-0000-{i:012d}" for i in range(201, 206)]
H_SZ = [f"a0000001-0000-0000-0000-{i:012d}" for i in range(301, 305)]

SERVICE_PRICE = {"full_accompany": 299.0, "half_accompany": 199.0, "errand": 149.0}

PAT_NAME = {
    P[0]: "测试患者A", P[1]: "测试患者B", P[2]: "测试患者C",
    P[3]: "张先生", P[4]: "李女士", P[5]: "王大爷",
    P[6]: "刘阿姨", P[7]: "赵女士", P[8]: "孙先生", P[9]: "周阿姨",
}
COM_NAME = {
    C[0]: "测试陪诊师A", C[1]: "测试陪诊师B", C[2]: "测试陪诊师C",
    C[3]: "王秀英", C[4]: "赵建国", C[5]: "钱丽华",
    C[6]: "孙伟明", C[7]: "周雪梅", C[8]: "吴志远", C[9]: "郑美玲",
}
HOSP_NAME = {
    H_BJ[0]: "北京协和医院", H_BJ[1]: "北京大学第一医院", H_BJ[2]: "中日友好医院",
    H_BJ[3]: "北京天坛医院", H_BJ[4]: "首都医科大学宣武医院", H_BJ[5]: "北京儿童医院",
    H_BJ[6]: "北京朝阳医院", H_BJ[7]: "北京积水潭医院",
    H_SH[0]: "复旦大学附属中山医院", H_SH[1]: "上海交通大学附属瑞金医院",
    H_SH[2]: "上海儿童医学中心", H_SH[3]: "华山医院", H_SH[4]: "上海市第一人民医院",
    H_GZ[0]: "中山大学附属第一医院", H_GZ[1]: "广州市第一人民医院",
    H_GZ[2]: "广东省人民医院", H_GZ[3]: "广州市妇女儿童医疗中心",
    H_GZ[4]: "南方医科大学南方医院",
    H_SZ[0]: "深圳市人民医院", H_SZ[1]: "北京大学深圳医院",
    H_SZ[2]: "深圳市儿童医院", H_SZ[3]: "深圳市第二人民医院",
}

# ---------------- Orders ----------------
# Each tuple: (order_no, patient, companion_or_None, hospital, svc_type, status,
#              appt_date, appt_time, desc, created_at_offset(str sql), expires_at(str))
O = []

def add(patient, companion, hospital, svc, status, date, tm, desc,
        created_offset="interval '1 hour'", expires="NULL"):
    idx = len(O) + 1
    O.append((idx, patient, companion, hospital, svc, status, date, tm, desc,
              created_offset, expires))

# created x 5 (last one is broadcast: companion=None)
add(P[0], None, H_BJ[0], "full_accompany", "created", "2026-04-20", "08:30",
    "第一次来协和看内科，不熟悉流程", "interval '5 minutes'",
    "NOW() + interval '25 minutes'")
add(P[1], None, H_SH[0], "half_accompany", "created", "2026-04-21", "09:00",
    "陪同老人去中山医院做体检", "interval '10 minutes'",
    "NOW() + interval '20 minutes'")
add(P[2], None, H_GZ[0], "full_accompany", "created", "2026-04-22", "07:30",
    "中山一院看骨科，需要轮椅", "interval '15 minutes'",
    "NOW() + interval '15 minutes'")
add(P[3], None, H_BJ[3], "errand",         "created", "2026-04-20", "10:00",
    "代取检查报告和药品", "interval '20 minutes'",
    "NOW() + interval '10 minutes'")
# 即将过期（未来 25-29 分钟）
add(P[4], None, H_SH[2], "full_accompany", "created", "2026-04-23", "08:00",
    "广播订单: 上海儿童医学中心", "interval '1 minute'",
    "NOW() + interval '29 minutes'")

# accepted x 5
for i in range(5):
    add(P[i % 10], C[i % 10], [H_BJ[1], H_SH[1], H_GZ[1], H_BJ[6], H_SZ[0]][i],
        ["full_accompany", "half_accompany", "errand", "full_accompany", "half_accompany"][i],
        "accepted", "2026-04-25", "09:00",
        f"已接单场景{i+1}", f"interval '{(i+1)*10} minutes'",
        "NOW() + interval '2 hours'")

# in_progress x 3
for i in range(3):
    add(P[i + 3], C[(i + 3) % 10], [H_BJ[2], H_SH[3], H_GZ[2]][i],
        "full_accompany", "in_progress", "2026-04-17", "08:30",
        f"服务进行中{i+1}", f"interval '{i+1} hours'", "NULL")

# completed x 10
for i in range(10):
    hos = [H_BJ[0], H_BJ[1], H_SH[0], H_GZ[0], H_SZ[0],
           H_BJ[2], H_SH[1], H_GZ[1], H_BJ[3], H_SH[2]][i]
    svc = ["full_accompany", "half_accompany", "errand"][i % 3]
    add(P[i % 10], C[i % 10], hos, svc, "completed",
        "2026-04-10", "08:00", f"已完成订单{i+1}",
        f"interval '{i+1} days'", "NULL")

# cancelled_by_patient x 3
for i in range(3):
    add(P[i], C[i], [H_BJ[4], H_SH[4], H_GZ[3]][i],
        "half_accompany", "cancelled_by_patient", "2026-04-12", "10:00",
        f"患者取消{i+1}", f"interval '{i+2} days'", "NULL")

# rejected_by_companion x 2
for i in range(2):
    add(P[i+5], C[i+5], [H_BJ[5], H_SH[2]][i], "full_accompany",
        "rejected_by_companion", "2026-04-13", "09:00",
        f"陪诊师拒单{i+1}", f"interval '{i+3} days'", "NULL")

# expired x 3 (带过去的 expires_at)
for i in range(3):
    add(P[i+3], None, [H_BJ[6], H_GZ[4], H_SZ[3]][i], "errand",
        "expired", "2026-04-14", "11:00",
        f"已过期广播订单{i+1}", f"interval '{i+4} days'",
        f"NOW() - interval '{i*3 + 1} days'")

# cancelled_by_companion x 2
for i in range(2):
    add(P[i+1], C[i+7], [H_BJ[7], H_SH[3]][i], "half_accompany",
        "cancelled_by_companion", "2026-04-14", "14:00",
        f"陪诊师取消{i+1}", f"interval '{i+2} days'", "NULL")

# refunded: project 中没有 refunded 状态 enum, 用 payments.refund 体现退款
# (order 状态仍是 cancelled_by_patient, 但 payment 有 refund 记录)

# 即将过期的活跃订单（accepted, expires_at 在未来 20-30 分钟）
add(P[7], C[2], H_SZ[1], "full_accompany", "accepted",
    "2026-04-17", "23:30", "即将过期活跃订单 1",
    "interval '2 minutes'", "NOW() + interval '22 minutes'")
add(P[8], C[3], H_BJ[0], "full_accompany", "accepted",
    "2026-04-17", "23:45", "即将过期活跃订单 2",
    "interval '3 minutes'", "NOW() + interval '27 minutes'")

# reviewed x 3 (已评价订单) — 选取前 3 个 completed 订单的 patient
# 这 3 个会同时在 reviews 表插入
# 已在 completed 范围内。我们直接把 completed[0..2] 的 status 设为 reviewed
for k in range(3):
    target_idx = 5 + 5 + 3 + k  # created(5)+accepted(5)+in_progress(3)+completed k
    O[target_idx] = list(O[target_idx])
    O[target_idx][5] = "reviewed"
    O[target_idx] = tuple(O[target_idx])

print("-- ============================================================================")
print("-- orders")
print("-- ============================================================================")
print("INSERT INTO orders (id, order_number, patient_id, companion_id, hospital_id, "
      "service_type, status, appointment_date, appointment_time, description, price, "
      "hospital_name, companion_name, patient_name, expires_at, created_at, updated_at) VALUES")
rows = []
for (idx, p, c, h, svc, st, date, tm, desc, co, exp) in O:
    oo = oid(idx)
    no = f"YLA20260417{idx:04d}"
    cstr = f"'{c}'" if c else "NULL"
    cname = f"'{COM_NAME.get(c,'未知')}'" if c else "NULL"
    desc_sql = desc.replace("'", "''")
    rows.append(
        f"('{oo}', '{no}', '{p}', {cstr}, '{h}', '{svc}', '{st}', '{date}', '{tm}', "
        f"'{desc_sql}', {SERVICE_PRICE[svc]}, '{HOSP_NAME[h]}', {cname}, "
        f"'{PAT_NAME[p]}', {exp}, NOW() - {co}, NOW() - {co})"
    )
print(",\n".join(rows) + ";")
print()

# ---------------- Chat messages ----------------
# 选 5 个订单，每个 12-14 条消息 → 至少 60 条
chat_targets = []
# accepted[0] idx=6, in_progress[0] idx=11, completed[0] idx=14 (reviewed) 仍可有聊天,
# completed[3] idx=17, completed[5] idx=19
for order_idx, pat, com in [(6, P[0], C[0]), (11, P[3], C[3]),
                            (14, P[0], C[0]), (17, P[3], C[3]),
                            (19, P[5], C[5])]:
    chat_targets.append((order_idx, pat, com))

print("-- ============================================================================")
print("-- chat_messages (共 ~65 条, 覆盖多订单/已读未读/系统消息)")
print("-- ============================================================================")
print("INSERT INTO chat_messages (id, order_id, sender_id, type, content, is_read, created_at) VALUES")
crows = []
cmid = 1
for order_idx, pat, com in chat_targets:
    dialogue = [
        (pat, "text", "您好，我预约了明天上午的陪诊服务"),
        (com, "text", "您好，已收到您的订单，请问有什么特殊注意事项？"),
        (pat, "text", "老人行动不便，可能需要轮椅"),
        (com, "text", "好的，我会提前到医院准备轮椅"),
        (pat, "text", "非常感谢"),
        (com, "text", "不客气，这是我应该做的"),
        (pat, "text", "需要空腹吗？"),
        (com, "text", "是的，建议早上不要吃东西"),
        (pat, "text", "好的，还有什么需要准备的？"),
        (com, "text", "带齐身份证、医保卡和既往病历即可"),
        (pat, "text", "明白了"),
        (com, "text", "明早7:30我在医院门口等您"),
        (com, "system", "订单状态已变更"),
    ]
    for i, (sender, typ, content) in enumerate(dialogue):
        is_read = "true" if (order_idx >= 14 or i < len(dialogue) - 3) else "false"
        order_uuid = oid(order_idx)
        content_sql = content.replace("'", "''")
        ts_offset = f"interval '{(len(dialogue) - i) * 3} minutes'"
        crows.append(
            f"('{cid(cmid)}', '{order_uuid}', '{sender}', '{typ}', '{content_sql}', "
            f"{is_read}, NOW() - {ts_offset})"
        )
        cmid += 1
print(",\n".join(crows) + ";")
print()

# ---------------- Notifications (>=30) ----------------
print("-- ============================================================================")
print("-- notifications (~35 条, 覆盖全部 NotificationType)")
print("-- ============================================================================")
print("INSERT INTO notifications (id, user_id, type, title, body, reference_id, is_read, created_at) VALUES")
nrows = []
nmid = 1

notif_types = [
    ("order_status_changed", "订单状态更新", "您的订单已被陪诊师接单"),
    ("new_message", "新消息", "您有一条新的聊天消息"),
    ("new_order", "新订单", "您有一个新的陪诊订单"),
    ("review_received", "新评价", "您收到一条新的评价"),
    ("start_service_request", "开始服务请求", "陪诊师请求开始服务"),
    ("system", "系统公告", "平台维护通知：本周六凌晨 2-4 点系统升级"),
]

# 每个类型 5-6 条，分配给不同用户，已读/未读混合
users_pool = P[:10] + C[:6]
for t, title, body in notif_types:
    for k in range(6):
        u = users_pool[(nmid + k) % len(users_pool)]
        ref = oid(((nmid - 1) % 28) + 1)
        is_read = "true" if k % 2 == 0 else "false"
        ts = f"interval '{nmid * 15} minutes'"
        nrows.append(f"('{nid(nmid)}', '{u}', '{t}', '{title}', '{body}', "
                     f"'{ref}', {is_read}, NOW() - {ts})")
        nmid += 1
print(",\n".join(nrows) + ";")
print()

# ---------------- Payments (>=15) ----------------
print("-- ============================================================================")
print("-- payments (~18 条, 覆盖 pending/success/failed + refund)")
print("-- ============================================================================")
print("INSERT INTO payments (id, order_id, user_id, amount, payment_type, status, created_at) VALUES")
prows = []
pmid = 1
# 10 completed 订单 → 都有 pay success
completed_start = 5 + 5 + 3  # created + accepted + in_progress
for k in range(10):
    idx = completed_start + k + 1
    o = oid(idx)
    u = O[idx - 1][1]  # patient
    svc = O[idx - 1][4]
    price = SERVICE_PRICE[svc]
    prows.append(
        f"('{pid(pmid)}', '{o}', '{u}', {price}, 'pay', 'success', "
        f"NOW() - interval '{k+1} days')"
    )
    pmid += 1
# 2 个 pending
for k in range(2):
    idx = 6 + k  # accepted 前 2 个
    o = oid(idx)
    u = O[idx - 1][1]
    prows.append(
        f"('{pid(pmid)}', '{o}', '{u}', 199.0, 'pay', 'pending', "
        f"NOW() - interval '2 hours')"
    )
    pmid += 1
# 2 个 failed
for k in range(2):
    idx = 11 + k  # in_progress 区
    o = oid(idx)
    u = O[idx - 1][1]
    prows.append(
        f"('{pid(pmid)}', '{o}', '{u}', 299.0, 'pay', 'failed', "
        f"NOW() - interval '{k+1} hours')"
    )
    pmid += 1
# 2 个 refund (对应 cancelled_by_patient)
cancel_start = completed_start + 10 + 1
for k in range(2):
    idx = cancel_start + k
    o = oid(idx)
    u = O[idx - 1][1]
    prows.append(
        f"('{pid(pmid)}', '{o}', '{u}', 199.0, 'refund', 'success', "
        f"NOW() - interval '{k+2} days')"
    )
    pmid += 1
# 2 个额外 pay (reviewed 订单)
for k in range(2):
    idx = completed_start + 1 + k  # reviewed 是 completed[0..2]
    # 但 reviewed 订单已经有 pay 了, 跳过以免 uq_payment_order_type 冲突
    pass
print(",\n".join(prows) + ";")
print()

# ---------------- Reviews (>=10) ----------------
print("-- ============================================================================")
print("-- reviews (~12 条, 多星级, 含匿名)")
print("-- ============================================================================")
print("INSERT INTO reviews (id, order_id, patient_id, companion_id, rating, content, "
      "patient_name, created_at) VALUES")
rrows = []
rmid = 1
# 10 completed 订单都给评价
for k in range(10):
    idx = completed_start + k + 1
    order = O[idx - 1]
    oo = oid(idx)
    p = order[1]
    c = order[2]
    rating = [5, 4, 5, 3, 5, 4, 5, 4, 3, 5][k]
    comments = [
        "服务非常专业，耐心细致，强烈推荐！",
        "整体不错，就是等待时间稍长",
        "陪诊师很贴心，帮了大忙",
        "服务一般，希望下次更好",
        "非常满意，全程无忧",
        "流程熟练，效率高",
        "超出预期，服务很好",
        "还可以，基本满足需求",
        "有待改进，但态度还行",
        "五星好评，下次还会再来",
    ]
    # 第 k=3、8 为匿名评价 (patient_name=NULL)
    pname_sql = "NULL" if k in (3, 8) else f"'{PAT_NAME[p]}'"
    rrows.append(
        f"('{rid(rmid)}', '{oo}', '{p}', '{c}', {rating}, '{comments[k]}', "
        f"{pname_sql}, NOW() - interval '{k+1} days')"
    )
    rmid += 1
# 再加 2 条: 3 星和 4 星额外
# 没有更多 completed 订单了, 就加到 reviewed (idx 14/15/16 中还没 review 的)  skip
print(",\n".join(rrows) + ";")
print()

# ---------------- Order status history (可选, ~20 条) ----------------
print("-- ============================================================================")
print("-- order_status_history (审计日志, 关键订单的状态迁移)")
print("-- ============================================================================")
print("INSERT INTO order_status_history (id, order_id, from_status, to_status, "
      "changed_by, note, created_at) VALUES")
hrows = []
hmid = 1
# 对 accepted/in_progress/completed 订单各记录几条迁移
# accepted[0]: idx=6
for idx in [6, 7, 8, 11, 12, 14, 15, 16, 17, 18]:
    order = O[idx - 1]
    oo = oid(idx)
    p = order[1]
    c = order[2] or p
    cur_status = order[5]
    # 简化: 从 created 到当前
    chain = ["created"]
    if cur_status in ("accepted", "in_progress", "completed", "reviewed"):
        chain.append("accepted")
    if cur_status in ("in_progress", "completed", "reviewed"):
        chain.append("in_progress")
    if cur_status in ("completed", "reviewed"):
        chain.append("completed")
    if cur_status == "reviewed":
        chain.append("reviewed")
    for i in range(1, len(chain)):
        hrows.append(
            f"('{hid(hmid)}', '{oo}', '{chain[i-1]}', '{chain[i]}', "
            f"'{c}', '自动迁移', NOW() - interval '{max(1, 5-i)} days')"
        )
        hmid += 1

print(",\n".join(hrows) + ";")
print()
