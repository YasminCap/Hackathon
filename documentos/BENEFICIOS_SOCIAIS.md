# LeakFinder Londrina — Benefícios sociais

> Material de apoio ao pitch do SmartCities Hackathon Londrina 2026.
> O protótipo é focado em **escolas municipais e CMEIs**, mas a **visão é municipal**: depois,
> todos os prédios da prefeitura e, em parceria com a Sanepar, a rede da cidade.
> Números de exemplo do protótipo são **simulados**; dados oficiais têm a fonte ao final.

---

## Em uma frase

**O LeakFinder Londrina transforma a conta de água do mês em informação de meia em meia hora: a
prefeitura deixa de pagar por vazamentos que ninguém via, protege os serviços essenciais da
falta d'água e ajuda a cidade a usar melhor um recurso que já está escasso.**

---

## 1. O problema, em números

| Dado | Valor | Fonte |
|---|---|---|
| Água tratada que o Brasil perde **antes de chegar às casas** | **37,78%** (2022) | Trata Brasil, Estudo de Perdas 2024 (base SNIS 2022) [1] [2] |
| Índice nacional mais recente | **39,53%** | Trata Brasil, relatório divulgado em 02/06/2026 [3] |
| Índice do **Paraná** | **33,40%** — melhor que a média, mas acima da meta | Trata Brasil, via Agência Estadual de Notícias [3] |
| Meta federal de perdas aceitáveis | **no máximo 25%** | Portaria 490/2021 do MDR [1] |
| Água perdida só em **vazamentos** no Brasil | **3,6 bilhões de m³** — abasteceria **~54 milhões de brasileiros por um ano** | Trata Brasil, Estudo de Perdas 2024 [1] |
| Brasileiros ainda **sem abastecimento de água** | **32 milhões** | Trata Brasil, Estudo de Perdas 2024 [1] |
| **Londrina** na crise hídrica | **Abril de 2021 foi o mais seco da história** da cidade; o Paraná decretou emergência hídrica | Agência Estadual de Notícias [4] |

> **Londrina:** não encontramos um índice oficial e recente de perdas só do município. Antes de
> citar, conferir no SINISA/SNIS (Ministério das Cidades) ou no relatório de transparência da Sanepar.

**O recado:** a água já é escassa (o Paraná viveu anos de estiagem e rodízio) e uma parte grande
dela se perde no caminho. Cada litro desperdiçado faz falta para alguém.

---

## 2. Onde a água se perde — e onde o LeakFinder Londrina entra

```
 Estação de       Rede pública (Sanepar)          Hidrômetro         Dentro do prédio
 tratamento  ───►  canos, reservatórios,  ───►    do prédio    ───►  canos, caixa d'água,
                   bombas, ligações                                  torneiras, descargas
                   ▲                                                  ▲
                   PERDA NA DISTRIBUIÇÃO                              DESPERDÍCIO INTERNO
                   (os ~38% dos números acima)                        (vazamentos que a conta
                   → visão municipal / parceria                        do mês esconde)
                                                                      → O QUE O PROTÓTIPO FAZ HOJE
```

- **Hoje (protótipo):** o LeakFinder Londrina vigia a água **depois do hidrômetro**, dentro dos prédios
  públicos. Essa água é paga pela prefeitura, com dinheiro de todos.
- **Visão municipal:** a mesma tecnologia, barata e sem obra, pode ajudar a enxergar também as
  perdas **antes** de a água chegar às casas, em parceria com a Sanepar (seção 4).

---

## 3. Benefícios sociais já com a proposta atual

### 3.1 Menos desperdício = mais água para a cidade
Um vazamento de madrugada numa escola pode correr por semanas, porque só aparece na conta do mês
seguinte. Com uma foto do hidrômetro a cada 30 minutos, ele é percebido em **cerca de 1 hora**.

**Exemplo simulado (protótipo):** uma torneira esquecida aberta a 7 litros por minuto.

| | Sem o sistema (descoberta na conta, ~30 dias) | Com o LeakFinder Londrina (~1h30) |
|---|---|---|
| Água perdida | ~302 mil litros | ~630 litros |

Em época de estiagem, essa é água que **fica no reservatório para a população**.

### 3.2 Dinheiro público de volta para o que importa
Água que vaza é água paga. Cada vazamento interrompido cedo é verba que deixa de ir para o ralo e
pode voltar para **merenda, material escolar, remédios e manutenção**. O painel mostra a perda
estimada de cada ocorrência, para a gestão enxergar o tamanho do problema.

### 3.3 Serviços essenciais funcionando: escola, creche e posto de saúde com água
Sem água, uma escola ou um CMEI **suspende as aulas** — e as famílias que dependem da creche
ficam sem onde deixar as crianças. Na fase 2, o mesmo vale para as UBS e o atendimento de saúde.
Monitorar o consumo de meia em meia hora permite agir antes do problema virar notícia:
- um cano rompido no meio do expediente vira alerta e ordem de serviço em minutos;
- *(evolução prevista)* um prédio **sem entrada de água** — falta na rede ou boia travada — é
  detectado antes de a caixa d'água esvaziar, e a prefeitura pode **priorizar caminhão-pipa**
  para quem não pode parar, como os CMEIs (e, na fase 2, as UBS).

### 3.4 Gestão pública baseada em dados, com transparência
Hoje a prefeitura só sabe quanto cada prédio gastou **no mês**. Com o LeakFinder Londrina ela sabe
**quando**, **onde** e **quanto** — e pode:
- priorizar reformas e investimentos (torneiras econômicas, reaproveitamento de água da chuva)
  onde o consumo está acima do esperado para aquele tipo de prédio;
- programar limpezas e regas fora dos horários de maior demanda da cidade;
- prestar contas à população com números, não com estimativas.

### 3.5 Sem obra, sem trocar medidor e sem tomada
A câmera (ESP32-CAM) **fotografa o hidrômetro que já existe**. Não corta cano, não troca
medidor, não interrompe o abastecimento. Isso torna a solução **barata e rápida de espalhar**
pela rede municipal — condição para o benefício social chegar a escala.

E ela **não depende da rede elétrica**: funciona com **bateria e painel solar**. Não é preciso levar tomada até o hidrômetro, que costuma ficar no muro ou na calçada. Se a bateria acabar, nenhum litro se perde: o hidrômetro continua marcando e a próxima foto recupera o total.

---

## 4. Visão municipal: das escolas para a cidade inteira

| Fase | Onde | Benefício principal |
|---|---|---|
| **1. Piloto** *(o protótipo)* | Escolas e CMEIs | Vazamentos detectados em ~1 h; serviço essencial protegido |
| **2. Prédios municipais** | Secretarias, UBS, ginásios, centros culturais, CRAS... | Gestão de toda a água paga pela prefeitura num só painel |
| **3. Parceria com a Sanepar** *(ideia futura)* | Bairros e setores da rede | Ajudar a localizar **perdas antes de a água chegar às casas** |

**Como a fase 3 ajudaria na distribuição e nas perdas da rede (ideia para discutir com a Sanepar):**
- **Balanço por bairro:** se a quantidade de água que **entra** num bairro é muito maior que a soma
  do que os imóveis **consomem**, a diferença é perda na rede daquele bairro. Leituras frequentes e
  baratas dos medidores ajudam a fechar essa conta mais vezes e a apontar onde procurar.
- **Mapa de consumo por hora e região:** dados que apoiam o planejamento de reservatórios,
  pressões e manobras, especialmente em estiagem.
- **Prédios públicos como sentinelas:** espalhados por todos os bairros, eles podem indicar
  rapidamente onde há falta de abastecimento (vários prédios da mesma região sem entrada de água
  ao mesmo tempo).

> A Sanepar já investe em detecção de vazamentos na rede, com sensores de ruído e inteligência
> artificial [5] [6]. A proposta é **somar** a esse esforço com dados de consumo, não substituí-lo.
> A operação da rede é da Sanepar; o LeakFinder Londrina é uma ferramenta de gestão para a prefeitura.

---

## 5. Alinhamento com compromissos públicos

- **ODS 6 — Água potável e saneamento:** uso eficiente da água e redução de desperdício.
- **ODS 11 — Cidades e comunidades sustentáveis:** gestão pública baseada em dados.
- **Meta federal de perdas de até 25%** (Portaria 490/2021 do MDR): toda redução de desperdício
  ajuda a cidade a caminhar nessa direção.

---

## 6. Frases prontas para o pitch

- "O Brasil perde perto de 4 em cada 10 litros de água tratada antes de ela chegar às casas. Quem
  cuida da água pública precisa enxergar onde ela está indo."
- "Hoje um vazamento numa escola só aparece na conta do mês seguinte. Com o LeakFinder Londrina, em cerca
  de uma hora."
- "Não trocamos medidor, não quebramos parede e não precisamos de tomada: uma câmera de baixo custo, com bateria e painel solar, lê o hidrômetro que já existe."
- "Começamos pelas escolas, mas a visão é municipal: todos os prédios públicos e, com a Sanepar,
  a rede da cidade."
- "Em abril de 2021, Londrina viveu o abril mais seco da sua história. Água desperdiçada é água
  que falta."

### O que evitar dizer
- Que o projeto **controla a rede** ou **distribui** a água — isso é da Sanepar.
- Números de economia **reais** em R$ ou litros — no protótipo eles são **simulados**.
- Dados de Londrina sem fonte oficial conferida.

---

## Fontes

Consultadas em 14/11/2026.

1. Instituto Trata Brasil — *Estudo de Perdas de Água 2024 (SNIS, 2022)*, conforme Agência iNFRA,
   05/06/2024: <https://agenciainfra.com/blog/ineficiencia-no-controle-de-perdas-de-agua-pode-afetar-a-universalizacao-do-saneamento-diz-trata-brasil/>
   — Release do estudo: <https://tratabrasil.org.br/wp-content/uploads/2024/06/Release-Perdas-de-Agua-2024.pdf>
2. Olhar Digital, 05/06/2024 — *Água desperdiçada no Brasil…*:
   <https://olhardigital.com.br/2024/06/05/ciencia-e-espaco/agua-desperdicada-no-brasil-poderia-abastecer-mais-de-50-milhoes-de-casas/>
3. Agência Estadual de Notícias do Paraná, 03/06/2026 — *Paraná tem duas cidades com os menores
   índices de perdas de água do Brasil*: <https://www.parana.pr.gov.br/aen/Noticia/Parana-tem-duas-cidades-com-os-menores-indices-de-perdas-de-agua-do-Brasil>
4. Agência Estadual de Notícias do Paraná, 04/05/2021 — *Governo decreta situação de emergência
   hídrica na RMC e no Sudoeste* (Decreto 7.554/21; Londrina entre as cidades com o abril mais seco
   da história): <https://www.parana.pr.gov.br/aen/Noticia/Governo-decreta-situacao-de-emergencia-hidrica-na-RMC-e-no-Sudoeste>
5. Agência Estadual de Notícias do Paraná — *Sanepar utiliza Inteligência Artificial para detectar
   vazamentos*: <https://www.parana.pr.gov.br/aen/Noticia/Sanepar-utiliza-Inteligencia-Artificial-para-detectar-vazamentos>
6. Agência Estadual de Notícias do Paraná — *Sanepar investe em solução inovadora para monitorar
   ruídos e detectar vazamentos de água*: <https://www.parana.pr.gov.br/Audio/Sanepar-investe-em-solucao-inovadora-para-monitorar-ruidos-e-detectar-vazamentos-de-agua>
