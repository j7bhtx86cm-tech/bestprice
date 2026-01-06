# ПОЛНЫЙ ОТЧЁТ ПРАВИЛ СИСТЕМЫ BESTPRICE
## Дата: 2026-01-06
## Версия: v12 (Geography Cascade)

---

# 1. PIPELINE ПОИСКА (Последовательность фильтров)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. PRODUCT_CORE FILTER (STRICT)                             │
│    - Кандидат ДОЛЖЕН иметь тот же product_core_id           │
│    - Нет fallback на super_class                             │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. GUARDS FILTER                                             │
│    ├─ FORBIDDEN_KEYWORDS: Запрещённые слова для категории   │
│    ├─ REQUIRED_ANCHORS: Обязательные слова для категории    │
│    ├─ FORBIDDEN_CROSS_MATCHES: Запрещённые пары             │
│    └─ SEED_DICT_RULES: Атрибуты (fat%, grade, size)        │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. GEOGRAPHY/BRAND FILTER                                    │
│    ├─ GEO_AS_BRAND (Город > Регион > Страна)               │
│    └─ BRAND_CRITICAL (STRICT mode)                          │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. UNIT COMPATIBILITY                                        │
│    ├─ UNIT_TYPE match (WEIGHT vs VOLUME vs PIECE)           │
│    └─ PACK_OUTLIER (packs > 20 = reject)                    │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. PRICE SANITY CHECK                                        │
│    - Проверка адекватности цены по категории                │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. RANKING (Сортировка по total_cost)                       │
└─────────────────────────────────────────────────────────────┘
```

---

# 2. КЛАССИФИКАЦИЯ (universal_super_class_mapper.py)

## 2.1 GUARD RULES (Защита от ложных срабатываний)

Эти правила имеют **высший приоритет** и переопределяют автоматическую классификацию.

| Ключевое слово | Исключить категории | Назначить категорию |
|----------------|---------------------|---------------------|
| `бобы` | seafood | vegetables.beans |
| `эдамаме` | seafood | vegetables.beans |
| `горох` | seafood | vegetables.peas |
| `фасоль` | seafood | vegetables.beans |
| `чечевиц` | seafood | vegetables.lentils |
| `нут` | seafood | vegetables.chickpeas |
| `персик` | seafood | canned.фрукты |
| `ананас` | seafood | canned.фрукты |
| `груша` | seafood | canned.фрукты |
| `абрикос` | seafood | canned.фрукты |
| `бумага для выпечки` | staples, seafood, meat | disposables.paper |
| `бумага туалетная` | staples, seafood, meat | disposables.paper |
| `бумага рисов` | disposables | staples.rice_paper |
| `полотенц` | staples, seafood, meat | disposables.napkins |
| `салфетк` | staples, seafood, meat | disposables.napkins |
| `перчатк` | staples, seafood, meat | disposables.gloves |
| `пленк пищев` | staples, seafood, meat | disposables.film |
| `фольг` | staples, seafood, meat | disposables.foil |
| `чука` | seafood.shrimp | seafood.seaweed |
| `вакаме` | seafood.shrimp | seafood.seaweed |
| `нори` | seafood.shrimp | seafood.seaweed |
| `водоросл` | seafood.shrimp | seafood.seaweed |
| `горбуша` | seafood.shrimp | seafood.salmon |
| `тилапия` | seafood.shrimp | seafood.tilapia |
| `пангасиус` | seafood.shrimp | seafood.pangasius |

## 2.2 DIRECT MAPPINGS (Прямые соответствия)

Проверяются **ДО** guard rules. Имеют наивысший приоритет.

### Добавки/Специи
| Ключевое слово | Категория |
|----------------|-----------|
| `желатин` | additives.gelatin |
| `агар` | additives.agar |
| `пектин` | additives.pectin |
| `соль` | condiments.salt |
| `сахар` | staples.сахар |
| `дрожжи` | additives.yeast |
| `краситель` | additives.colorant |

### Рис
| Ключевое слово | Категория |
|----------------|-----------|
| `рис басмати` | staples.рис.басмати |
| `рис жасмин` | staples.рис.жасмин |
| `рис круглозерн` | staples.рис |
| `рис длиннозерн` | staples.рис |

### Мука (CRITICAL)
| Ключевое слово | Категория |
|----------------|-----------|
| `мука` | staples.мука |
| `мука пшеничная` | staples.мука.пшеничная |
| `мука ржаная` | staples.мука.ржаная |
| `мука кукурузная` | staples.мука.кукурузная |
| `мука рисовая` | staples.мука.рисовая |
| `мука гречневая` | staples.мука.гречневая |
| `макфа` | staples.мука |

### Крабы (CRITICAL - натуральный vs имитация)
| Ключевое слово | Категория |
|----------------|-----------|
| `краб камчат` | seafood.crab.kamchatka |
| `краб натур` | seafood.crab.natural |
| `king crab` | seafood.crab.king |
| `крабов палочк` | seafood.crab_sticks |
| `сурими` | seafood.crab_sticks |
| `снежный краб` | seafood.crab_sticks |

### Овощи
| Ключевое слово | Категория |
|----------------|-----------|
| `тыква` | vegetables.тыква |
| `кабачок` | vegetables.кабачок |
| `шпинат` | vegetables.spinach |
| `шампиньон` | vegetables.mushrooms |
| `грибы` | vegetables.mushrooms |

### Сиропы и напитки
| Ключевое слово | Категория |
|----------------|-----------|
| `сироп` | beverages.syrup |
| `кола` | beverages.cola |
| `эвервесс` | beverages.soft_drinks |
| `спрайт` | beverages.soft_drinks |
| `фанта` | beverages.soft_drinks |
| `лимонад` | beverages.lemonade |
| `газиров` | beverages.carbonated |
| `концентрат` | beverages.concentrate |

### Лапша/Паста
| Ключевое слово | Категория |
|----------------|-----------|
| `лапша` | pasta.noodles |
| `соба` | pasta.soba |
| `удон` | pasta.udon |
| `рамен` | pasta.ramen |
| `фунчоза` | pasta.glass_noodles |

### Орехи
| Ключевое слово | Категория |
|----------------|-----------|
| `миндал` | nuts.almonds |
| `фундук` | nuts.hazelnuts |
| `кешью` | nuts.cashews |
| `фисташ` | nuts.pistachios |
| `грецк` | nuts.walnuts |
| `арахис` | nuts.peanuts |
| `кедров` | nuts.pine_nuts |

### Сухофрукты
| Ключевое слово | Категория |
|----------------|-----------|
| `чернослив` | dried_fruits.prunes |
| `курага` | dried_fruits.apricots |
| `изюм` | dried_fruits.raisins |
| `инжир` | dried_fruits.figs |
| `финик` | dried_fruits.dates |

### Морепродукты
| Ключевое слово | Категория |
|----------------|-----------|
| `угорь` | seafood.eel |
| `судак` | seafood.pike_perch |
| `окунь` | seafood.perch |
| `гребеш` | seafood.scallop |
| `щука` | seafood.pike |
| `сайда` | seafood.pollock |
| `кета` | seafood.chum_salmon |
| `изумидай` | seafood.tilapia |

### Мясо
| Ключевое слово | Категория |
|----------------|-----------|
| `бекон` | meat.bacon |
| `стрипс` | meat.strips |
| `фрикадельк` | meat.meatballs |
| `пепперони` | meat.pepperoni |
| `паштет` | meat.pate |
| `байтс` | meat.bites |
| `голубц` | frozen.golubcy |

### Курица
| Ключевое слово | Категория |
|----------------|-----------|
| `грудк` | meat.chicken.breast |
| `бедр` | meat.chicken.thigh |
| `крыл` | meat.chicken.wings |
| `куриная` | meat.chicken |
| `кура` | meat.chicken |
| `курин` | meat.chicken |
| `цыпл` | meat.chicken |
| `бройлер` | meat.chicken |

### Ягоды (замороженные)
| Ключевое слово | Категория |
|----------------|-----------|
| `брусника` | frozen.berries |
| `облепиха` | frozen.berries |
| `клюква` | frozen.berries |
| `черника` | frozen.berries |
| `малина` | frozen.berries |
| `клубника` | frozen.berries |

### Одноразовая посуда
| Ключевое слово | Категория |
|----------------|-----------|
| `мешки` | disposables.bags |
| `стакан` | disposables.cups |
| `бутылка` | disposables.bottles |
| `коробка` | disposables.boxes |
| `крышк` | disposables.lids |

---

# 3. УЗКАЯ КЛАССИФИКАЦИЯ (product_core_classifier.py)

## 3.1 Правила для мяса

### meat.beef → product_core
| Ключевые слова | product_core |
|----------------|--------------|
| `фарш`, `minced`, `ground` | meat.beef.ground |
| `стейк`, `steak` | meat.beef.steak |
| `рибай`, `ribeye`, `rib-eye` | meat.beef.ribeye |
| `рёбр`, `ribs` | meat.beef.ribs |
| `филе`, `fillet`, `вырезка` | meat.beef.fillet |
| `грудк`, `brisket` | meat.beef.brisket |
| `суповой`, `soup`, `набор` | meat.beef.soup_set |
| `гуляш`, `stew` | meat.beef.stew |
| `котлет`, `burger`, `patty` | meat.beef.patty |

### meat.pork → product_core
| Ключевые слова | product_core |
|----------------|--------------|
| `фарш`, `minced`, `ground` | meat.pork.ground |
| `ребр`, `ribs` | meat.pork.ribs |
| `шейк`, `neck` | meat.pork.neck |
| `корейк`, `loin` | meat.pork.loin |
| `грудинк`, `belly` | meat.pork.belly |

### meat.chicken → product_core
| Ключевые слова | product_core |
|----------------|--------------|
| `фарш`, `minced`, `ground` | meat.chicken.ground |
| `грудк`, `breast` | meat.chicken.breast |
| `бедр`, `thigh` | meat.chicken.thigh |
| `крыл`, `wing` | meat.chicken.wing |
| `голен`, `drumstick` | meat.chicken.drumstick |
| `целая`, `whole` | meat.chicken.whole |

## 3.2 Правила для муки

### staples.мука → product_core
| Ключевые слова | product_core |
|----------------|--------------|
| `пшенич`, `wheat` | staples.flour.wheat |
| `ржан`, `rye` | staples.flour.rye |
| `кукуруз`, `corn` | staples.flour.corn |
| `рисов`, `rice` | staples.flour.rice |
| `гречнев`, `buckwheat` | staples.flour.buckwheat |
| `овсян`, `oat` | staples.flour.oat |
| `макарон`, `pasta`, `дурум` | staples.flour.durum |

## 3.3 Правила для соусов

### condiments.sauce → product_core
| Ключевые слова | product_core |
|----------------|--------------|
| `кетчуп`, `ketchup` | condiments.ketchup |
| `майонез`, `mayo` | condiments.mayo |
| `соев`, `soy` | condiments.soy_sauce |
| `томат`, `tomato` | condiments.tomato_sauce |
| `горчиц`, `mustard` | condiments.mustard |
| `барбекю`, `bbq`, `barbecue` | condiments.sauce.bbq |
| `терияки`, `teriyaki` | condiments.sauce.teriyaki |
| `кимчи`, `kimchi` | condiments.sauce.kimchi |
| `кисло-сладк`, `sweet.*sour` | condiments.sauce.sweet_sour |
| `цезар`, `caesar` | condiments.sauce.caesar |
| `карри`, `curry` | condiments.sauce.curry |
| `бальзамич`, `balsamic` | condiments.sauce.balsamic |
| `чили`, `chili` | condiments.sauce.chili |
| `шашлыч`, `marinade` | condiments.sauce.marinade |
| `бешамель`, `bechamel` | condiments.sauce.bechamel |
| `голландез`, `hollandaise` | condiments.sauce.hollandaise |

## 3.4 Правила для морепродуктов

### seafood.crab → product_core (CRITICAL)
| Ключевые слова | product_core |
|----------------|--------------|
| `камчат`, `kamchatka` | seafood.crab.kamchatka |
| `king crab`, `королевск` | seafood.crab.king |
| `натур` | seafood.crab.natural |
| `снежн`, `vici`, `вичи` | seafood.crab_sticks |
| `палочк`, `сурими`, `surimi`, `имит` | seafood.crab_sticks |

### seafood.squid → product_core
| Ключевые слова | product_core |
|----------------|--------------|
| `кальмар`, `squid`, `calamari` | seafood.squid |
| `тушк`, `body` | seafood.squid.body |
| `филе`, `fillet` | seafood.squid.fillet |
| `кольц`, `ring` | seafood.squid.rings |

## 3.5 Правила для сыра

### dairy.сыр → product_core
| Ключевые слова | product_core |
|----------------|--------------|
| `моцарелл`, `mozzarella` | dairy.cheese.mozzarella |
| `пармезан`, `parmesan` | dairy.cheese.parmesan |
| `чеддер`, `cheddar` | dairy.cheese.cheddar |
| `фета`, `feta` | dairy.cheese.feta |
| `брынз`, `brynza` | dairy.cheese.brynza |
| `сулугун`, `suluguni` | dairy.cheese.suluguni |
| `голланд`, `gouda`, `dutch` | dairy.cheese.dutch |
| `плавлен`, `processed` | dairy.cheese.processed |

---

# 4. GUARDS (p0_hotfix_stabilization.py)

## 4.1 NEGATIVE_KEYWORDS (Запрещённые слова)

Если кандидат содержит эти слова для данной категории → **ОТКЛОНИТЬ**.

| Категория | Запрещённые слова |
|-----------|-------------------|
| meat.beef | `растительн`, `веган`, `соев`, `заменител`, `тофу`, `substitute`, `сосиск`, `колбас` |
| meat.pork | `растительн`, `веган`, `соев`, `заменител` |
| meat.chicken | `растительн`, `веган`, `соев`, `заменител` |
| dairy.сыр | `сырник` |
| dairy.cheese | `сырник`, `cheesecake` |
| staples.flour.wheat | `ржан`, `rye`, `макарон`, `pasta` |
| staples.flour.rye | `пшенич`, `wheat` |

## 4.2 REQUIRED_ANCHORS (Обязательные слова)

Кандидат ДОЛЖЕН содержать хотя бы одно из этих слов → иначе **ОТКЛОНИТЬ**.

| Категория | Обязательные слова |
|-----------|-------------------|
| dairy.сыр | `сыр`, `cheese`, `mozzarella`, `моцарелл`, `пармезан`, `гауда`, `чеддер`, `фета`, `брынз`, `сулугун` |
| meat.beef | `говядин`, `beef` |
| meat.pork | `свинин`, `pork` |
| meat.chicken | `курин`, `chicken`, `цыпл`, `кура`, `бройлер` |
| meat.turkey | `индейк`, `turkey` |
| seafood.salmon | `лосос`, `семг`, `salmon`, `форел`, `нерк`, `кижуч`, `горбуш` |
| seafood.shrimp | `креветк`, `shrimp`, `prawn` |
| seafood.squid | `кальмар`, `squid`, `calamari` |
| seafood.seabass | `сибас`, `seabass` |
| seafood.pollock | `минтай`, `pollock` |
| seafood.crab | `краб`, `crab` |
| seafood.crab.kamchatka | `камчат`, `king crab`, `натур` |
| seafood.crab.natural | `натур`, `камчат`, `king` |
| seafood.crab_sticks | `палочк`, `сурими`, `surimi`, `имит`, `снежн` |
| condiments.ketchup | `кетчуп`, `ketchup` |
| condiments.mayo | `майонез`, `mayo` |
| condiments.wasabi | `васаби`, `wasabi` |
| staples.мука | `мука`, `flour` |
| staples.мука.пшеничная | `мука`, `flour`, `пшенич`, `wheat` |
| staples.мука.ржаная | `мука`, `flour`, `ржан`, `rye` |
| staples.flour.wheat | `пшенич`, `wheat` |
| staples.flour.rye | `ржан`, `rye` |

## 4.3 FORBIDDEN_CROSS_MATCHES (Запрещённые пары)

Эти пары **НИКОГДА** не должны матчиться.

| Категория Reference | Запрещённые слова в Candidate |
|--------------------|------------------------------|
| seafood.crab.kamchatka | `палочк`, `сурими`, `surimi`, `имит`, `снежн` |
| seafood.crab.natural | `палочк`, `сурими`, `surimi`, `имит`, `снежн` |
| seafood.crab_sticks | `камчат`, `натур`, `king crab` |
| seafood.squid | `курин`, `кура`, `chicken`, `цыпл`, `индейк`, `утк`, `гус` |
| seafood.shrimp | `говядин`, `свинин`, `курин`, `chicken` |
| seafood.salmon | `говядин`, `свинин`, `курин`, `chicken` |

## 4.4 DYNAMIC ANCHORS (Динамические якоря)

Для определённых категорий reference извлекаются **специфические атрибуты**, которые **ОБЯЗАНЫ** присутствовать в candidate.

### Размеры креветок
```
16/20, 21/25, 26/30, 31/35, 31/40, 41/50, 51/60, 61/70, 71/90, 90/120, 100/150, 150/200, 200/300, 300/500
```

### Типы специй
```
васаби, wasabi, соль, salt, нитритн, перец, pepper, горчиц, mustard, имбир, ginger, кунжут, sesame, кориандр, coriander, куркум, turmeric, паприк, paprika, базилик, basil, орегано, oregano, тимьян, thyme, розмарин, rosemary
```

### Типы муки
```
пшенич, wheat, ржан, rye, кукуруз, corn, рисов, rice, гречнев, buckwheat, овсян, oat
```

### Типы мяса
```
фарш, minced, ground, стейк, steak, филе, fillet, рёбр, ribs, грудк, breast, бедр, thigh
```

---

# 5. SEED_DICT_RULES (База правил из Excel)

**Всего правил в базе: 421**

## Распределение по типам:
| Тип | Количество |
|-----|------------|
| product | 166 |
| process | 36 |
| type | 31 |
| характеристика | 23 |
| form | 20 |
| grade | 18 |
| pack | 18 |
| cut | 17 |
| fat | 15 |
| size | 14 |
| метод | 8 |
| качество | 7 |
| species | 7 |
| service | 6 |
| liquid | 6 |
| state | 5 |
| temp | 4 |
| состояние | 4 |
| note | 4 |
| other | 3 |
| category | 3 |
| упаковка | 3 |
| sugar | 2 |
| продукт | 1 |

## Примеры использования:
- **fat** (жирность): "Молоко 3.2%" → кандидат должен содержать "3.2%"
- **grade** (сорт): "Говядина CHOICE" → кандидат должен содержать "choice"
- **size** (размер): "Креветки 16/20" → кандидат должен содержать "16/20"

---

# 6. PRICE SANITY CHECK (Проверка адекватности цен)

## Минимальные пороговые цены по категориям:

| Категория | Мин. цена (₽/кг) | Комментарий |
|-----------|------------------|-------------|
| seafood.crab.kamchatka | 2000 | Камчатский краб |
| seafood.crab.natural | 1500 | Натуральный краб |
| seafood.crab.king | 2500 | King crab |
| seafood.lobster | 2000 | Лобстер |
| meat.beef.ribeye | 1000 | Рибай |
| meat.beef.wagyu | 3000 | Вагю |
| seafood.crab_sticks | 50 | Крабовые палочки (дешёвый продукт) |

## Логика проверки:
1. Если категория есть в таблице → цена кандидата должна быть ≥ 50% от порога
2. Если отношение цен reference/candidate > 5 → проверить на "премиум" ключевые слова
3. Премиум слова: `натур`, `камчат`, `king`, `премиум`, `prime`, `choice`, `wagyu`

---

# 7. ГЕОГРАФИЯ (geography_extractor.py)

## 7.1 Приоритет фильтрации: **Город > Регион > Страна**

## 7.2 Страны (103 паттерна)

### СНГ
- РОССИЯ: `россия`, `рф`, `russian`, `russia`, `российск`, `отечествен`
- БЕЛАРУСЬ: `беларус`, `белорус`, `belarus`, `белоруссия`
- КАЗАХСТАН: `казахстан`, `kazakhstan`, `казах`
- И др. (Украина, Узбекистан, Армения, Грузия, Азербайджан, Молдова, Киргизия, Таджикистан, Туркменистан)

### Европа
- ГЕРМАНИЯ: `герман`, `germany`, `немецк`, `deutsche`
- ФРАНЦИЯ: `франц`, `france`, `french`
- ИТАЛИЯ: `итал`, `italy`, `italian`
- И др. (29 стран)

### Азия
- КИТАЙ: `китай`, `china`, `chinese`, `кнр`
- ЯПОНИЯ: `япони`, `japan`, `japanese`
- ВЬЕТНАМ: `вьетнам`, `vietnam`, `vietnamese`
- ТАИЛАНД: `таиланд`, `тайланд`, `thailand`, `thai`
- И др. (17 стран)

### Америка
- США: `сша`, `usa`, `америк`, `american`, `u.s.`
- АРГЕНТИНА: `аргентин`, `argentina`
- БРАЗИЛИЯ: `бразил`, `brazil`
- И др. (10 стран)

## 7.3 Регионы России (26 паттернов)
- МОСКОВСКАЯ ОБЛ.: `московск`, `подмосков`
- КРАСНОДАРСКИЙ КРАЙ: `краснодарск`, `кубан`, `кубань`
- КАМЧАТКА: `камчатк`, `камчатск`
- МУРМАНСКАЯ ОБЛ.: `мурманск`
- И др.

## 7.4 Города России (20 паттернов)
- МОСКВА: `москва`, `москов`, `moscow`
- САНКТ-ПЕТЕРБУРГ: `санкт-петербург`, `спб`, `петербург`, `питер`, `ленинград`
- МУРМАНСК: `мурманск`
- И др.

## 7.5 FALSE POSITIVES (Исключения)
| Паттерн | Контекст исключения |
|---------|---------------------|
| `чили` | `соус`, `перец`, `острый`, `сладкий`, `chili`, `chilli` |
| `голланд` | `соус`, `голландез`, `hollandaise` |
| `америк` | `стиль`, `style` |
| `мексик` | `стиль`, `style`, `микс` |
| `грец` | `орех`, `орешки` |
| `инди` | `стиль`, `style`, `карри` |

---

# 8. БРЕНДЫ (brand_extractor.py)

## 8.1 Известные бренды (210+ записей)

### Международные бренды
- Heinz, Knorr, Hellmann's, Tamaki, Kotanyi, Aroy-D, Barinoff, Monin

### Российские бренды
- Агро-Альянс, Колобок, Националь, Простоквашино, Домик в деревне, Макфа, Мираторг, Черкизово

### Азиатские бренды
- Kikkoman, Genso, Kingzest, Sen Soy, PRB, Chang, Yoshimi

### Специи/Приправы
- SpiceExpert, Pikador, Provil

### Масла
- Sunny Gold, Ideal, Granoliva, Borges, Filippo Berio

### Молочные
- Unagrande, President, Galbani, Parmalat, Valio

### Морепродукты
- Vici, Санта Бремор, Polar, Agama

### Кондитерские
- Irca, Callebaut, Puratos, Lesaffre

### Консервы
- Mamminger, Bonduelle, Horeca Select, Metro Chef

## 8.2 Исключения из брендов
**Страны (не бренды):**
```
россия, рф, китай, китая, чили, таиланд, вьетнам, india, индия, италия, испания, германия, франция, сша, usa, беларусь, казахстан, турция, греция, норвегия, peru, перу
```

**Не-брендовые слова:**
```
пэт, стекло, ст/б, ж/б, вес, шт, уп, упак, гост, категория, сорт, экстра, премиум, premium, extra, заморозка, охлажд, с/м, классический, традиционный, натуральный, красный, белый, черный, зеленый, желтый, копчен, соленый, сушеный
```

---

# 9. UNIT NORMALIZER (unit_normalizer.py)

## 9.1 Типы единиц
- **WEIGHT**: kg, g, кг, г, гр
- **VOLUME**: l, ml, л, мл
- **PIECE**: pcs, шт, штук, уп, упак

## 9.2 Правила совместимости
| Тип Reference | Совместимые типы Candidate |
|---------------|---------------------------|
| WEIGHT | WEIGHT |
| VOLUME | VOLUME |
| PIECE | PIECE |

## 9.3 Покрытие парсинга: **95%**

---

# 10. СТАТИСТИКА ПОКРЫТИЯ ДАННЫХ

## По состоянию на 2026-01-06:

| Метрика | Значение |
|---------|----------|
| Всего активных товаров | 8218 |
| Покрытие product_core | 100% |
| Покрытие super_class | 100% |
| Покрытие brand_id | 100% |
| - High confidence (≥0.8) | 35% |
| - Medium confidence (0.6-0.8) | 18% |
| - Low confidence (<0.6) | 47% |
| Покрытие origin_country | 22.7% |
| Покрытие origin_region | 1.2% |
| Покрытие origin_city | 0.6% |
| Категория "other" | 2.1% |
| Low core confidence | 9% |
| Pack parsing | 95% |

---

# КОНЕЦ ОТЧЁТА
