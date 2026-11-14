# LeakFinder Londrina — Decisões do projeto e perguntas da banca

> Registro das decisões tomadas pelo time durante o SmartCities Hackathon Londrina 2026,
> com os motivos, o que ainda está em aberto e as perguntas que a banca pode fazer.
> Números do protótipo são **simulados**.

---

## Parte 1 — Decisões tomadas e motivos

### Escopo e cliente

| Data | Decisão | Motivo |
|---|---|---|
| 13/11 | **O cliente é a prefeitura** (modelo de governo, B2G). Nada de venda para pessoas ou kit residencial. | O tema do hackathon é gestão pública, e a prefeitura paga a água de todos os seus prédios. |
| 13/11 | **Protótipo só de software**; a leitura do hidrômetro é **simulada**. | No tempo do hackathon, o valor está em mostrar a detecção e a gestão. O simulador fala a mesma "língua" (MQTT) do dispositivo real, então trocar um pelo outro não muda o resto do sistema. |
| 13/11 | Todo dado de exemplo é marcado como **simulado**. | Transparência com a banca: nenhum número é apresentado como real. |
| 14/11 | **Foco do protótipo: escolas municipais (1º ao 5º ano) e CMEIs.** Os demais prédios (secretarias, UBS, esporte, cultura, CRAS) são a **fase 2**. | Escolas e CMEIs são uma rede grande, com horário bem definido (o que facilita achar vazamento fora do horário) e com impacto social direto. Manter o escopo enxuto deixa a demonstração clara. |
| 14/11 | **Visão municipal em 3 fases:** escolas e CMEIs → todos os prédios municipais → parceria com a Sanepar. | Mostra para onde o projeto cresce sem prometer o que o protótipo não faz. |
| 14/11 | **Nome do projeto: LeakFinder Londrina.** | Decisão do time. |

### O que ficou de fora (só como ideia futura no slide)

| Data | Ideia | Por que ficou de fora |
|---|---|---|
| 13/11 | **Escolas Guardiãs** (ranking de economia entre unidades) | Foco e prazo: não é essencial para mostrar a detecção. |
| 13/11 | **Auditor de contas da Sanepar + laudo PDF** | Foco e prazo; vira argumento de evolução ("R$ recuperados em contas erradas"). |
| 13/11 | **UPA e unidades 24h** | Nunca fecham, então precisam de outra regra (vazão mínima da madrugada). |
| 13/11 | **IA com dados reais** | Treinar com dados simulados só ensinaria o modelo a imitar o simulador. Faz sentido quando houver histórico real. |
| 14/11 | **Telegram e "fechar registro" a distância** | Foco no painel do gestor. Fechar a água a distância exigiria instalar uma **válvula elétrica** (obra) e poderia deixar uma escola sem água por engano; a decisão fica com as pessoas. |

### Hardware da versão real

| Data | Decisão | Motivo |
|---|---|---|
| 14/11 | **ESP32-CAM fotografando o mostrador do hidrômetro que já existe, a cada 30 min.** | Não corta cano, não troca medidor, não interrompe o abastecimento. É barata e rápida de instalar, e a foto serve de prova da leitura. |
| 14/11 | **Câmera com bateria e painel solar**, sem depender da rede elétrica. | O hidrômetro fica no muro ou na calçada, normalmente sem tomada perto. Fotos espaçadas (a cada 30 min) poupam bateria. |
| 14/11 | Uma foto a cada **30 minutos** (e não leitura contínua). | Para achar vazamento de madrugada, basta saber se o número sobe com o prédio fechado. Isso aparece em cerca de 1 hora, contra até 30 dias hoje, quando só aparece na conta. |

### Detecção de vazamentos

| Data | Decisão | Motivo |
|---|---|---|
| 13/11 | **Duas regras simples e explicáveis:** (1) consumo fora do horário de uso; (2) no horário de uso, consumo maior que 2× a média daquela faixa de horário da própria unidade. | A banca e o gestor entendem *por que* o alerta apareceu. |
| 13/11 | A média é calculada em **faixas de 15 minutos**, não em horas cheias. | Nos testes, a média por hora cheia gerava **alarmes falsos** na abertura e no fechamento das escolas. Com faixas de 15 min, os alarmes falsos sumiram. |
| 13/11 | A causa é apresentada como **"provável"** (descarga, boia, torneira, cano rompido), deduzida pela vazão. | O sistema não vê o cano: ele estima. Dizer "provável" é honesto. |
| 14/11 | Vazamento = consumo em **3 fotos seguidas** fora do horário (**2** no modo demonstração). | Uma foto isolada pode ser uso esporádico (vigia, limpeza). Três fotos seguidas indicam algo contínuo. |
| 14/11 | **Leitura suspeita é descartada** (total que diminui ou dá um salto impossível). | A leitura da foto pode errar um dígito. O hidrômetro só anda para a frente, então dá para perceber o erro; a próxima foto corrige. |
| 14/11 | Cada alerta tem um **campo de operação**: pendente → informado à manutenção → consertado. | O gestor acompanha o andamento de cada ocorrência no próprio painel. |

### Dados da simulação

| Data | Decisão | Motivo |
|---|---|---|
| 14/11 | **Consumo normal baseado em estudos medidos:** escolas **10 L/aluno/dia**, CMEIs **25 L/criança/dia**, com número de alunos fictício. | Tabelas de projeto usam 50 L/aluno/dia, mas servem para dimensionar a caixa d'água. Estudos que mediram escolas públicas encontraram cerca de 8 a 11 L/aluno/dia (ex.: Joinville, Brasília). Para creches não há estudo medido: 25 L é estimativa nossa, acima do mínimo de 20 L da UNICEF para período integral. |
| 14/11 | Na demonstração, o **tipo de vazamento é sorteado**. | Quem descobre a provável causa é o sistema, não quem apresenta. |

### Painel do gestor

| Data | Decisão | Motivo |
|---|---|---|
| 14/11 | Alerta marcado como **Consertado** vai para a aba escondida **Finalizados**. Se o vazamento parar mas ninguém marcar, ele continua visível. | A lista principal mostra só o que precisa de atenção, sem perder o registro; e nada some sem alguém confirmar o conserto. |
| 14/11 | **Consumo médio só por unidade**, sem o total somado de todas. | O total somado não ajuda o gestor a agir; o que importa é cada unidade. |
| 14/11 | **Histórico semanal** guardado e **média semanal de acompanhamento** por unidade (só semanas completas). | Permite ver tendência e comparar a semana atual com o normal daquela unidade. |
| 14/11 | **Demonstrativo de economia**: água não desperdiçada e valor poupado. Hipótese de **15 dias** sem o sistema (começou com 30; o time reduziu por achar exagerado); tarifa **R$ 7,00/m³** (tarifa média de água da Sanepar 2026, sem esgoto). | Mostra o retorno do projeto em litros e em reais. A tarifa sem esgoto deixa a estimativa conservadora. |
| 14/11 | **Cadastro de unidade** pelo painel; a unidade nova fica **aguardando câmera** até a instalação. | É assim na vida real: primeiro se cadastra, depois se instala o equipamento. |
| 14/11 | Cadastro **com endereço** (localizado no mapa pelo OpenStreetMap) e **sem número de alunos**. | O gestor sabe o endereço, não o consumo esperado. A média de cada unidade é **medida pelo consumo semanal registrado**; os "alunos" das unidades de exemplo só servem para o simulador gerar consumo realista. |

### Modelo de negócio

| Data | Decisão | Motivo |
|---|---|---|
| 14/11 | **Remuneração baseada na economia comprovada** (contrato de eficiência). | A prefeitura não gasta dinheiro novo: o sistema se paga com a água que deixa de vazar. Risco baixo para o poder público. Confirmar com a assessoria jurídica o modelo de contratação aplicável. |

### Forma de trabalho

| Data | Decisão | Motivo |
|---|---|---|
| 13/11 | Nada é enviado ao GitHub sem permissão; envios vão para uma **branch nova**, e o merge na `main` só acontece após confirmação, mantendo as datas dos commits. | Controle do que chega ao repositório do grupo; o histórico de commits prova o trabalho feito durante o evento. |

---

## Parte 2 — Questões ainda em aberto

| Questão | Opções | Observação |
|---|---|---|
| **Como a câmera se conecta à internet** perto do hidrômetro? | Wi-Fi da escola (com repetidor), chip de celular, rede de longo alcance | Sem tomada no local, o Wi-Fi da escola pode não alcançar o muro. |
| **Onde a foto vira número?** | Na própria câmera (ex.: projeto aberto *AI-on-the-edge-device*) ou no servidor | Na câmera, trafega só o número; no servidor, todas as fotos ficam guardadas. |
| **Números reais de alunos** e consumo das escolas de Londrina | Contas reais de algumas escolas, dados da Secretaria de Educação | Hoje os números são fictícios, baseados em estudos de outras cidades. |
| **Índice de perdas de água de Londrina** | SINISA/SNIS, relatório de transparência da Sanepar | Não encontramos dado oficial e recente só do município. |
| **Custo por unidade e percentual de remuneração** | Estudo de custos | Não citar valores no pitch. |
| **Correio MQTT privado** (HiveMQ Cloud) no dia | Configurar ou seguir no broker público de teste | No público, outro grupo poderia usar os mesmos nomes de tópico. |

---

## Parte 3 — Possíveis perguntas da banca (e respostas sugeridas)

### Sobre o funcionamento

**1. Como a foto vira número?**
A câmera fica fixa na frente do mostrador, então cada dígito aparece sempre no mesmo lugar da imagem. O sistema recorta cada dígito e um pequeno modelo de reconhecimento identifica o número. Já existem projetos abertos que fazem exatamente isso com a ESP32-CAM (ex.: *AI-on-the-edge-device*).

**2. E se a câmera ler um número errado?**
O hidrômetro só anda para a frente. Se a leitura "diminuir" ou der um salto impossível, ela é descartada, e a próxima foto traz o total certo. Isso já está no protótipo.

**3. E se a internet ou a bateria acabarem?**
Nenhum litro se perde: o hidrômetro continua marcando. O painel mostra a unidade como "sem sinal", e a primeira foto depois que tudo volta traz o total atualizado.

**4. Por que uma foto a cada 30 minutos? Não é pouco?**
Para achar vazamento basta saber se o número sobe quando a escola está fechada. Com 3 fotos seguidas, o vazamento aparece em cerca de 1 hora, contra até 30 dias hoje (na conta). Fotos espaçadas também poupam bateria e internet.

**5. E vazamento durante a aula, quando a escola está usando água?**
A segunda regra compara o consumo com a média daquele horário da própria unidade: um cano rompido aparece como "consumo excessivo". Vazamentos pequenos durante a aula se misturam ao uso normal, mas aparecem à noite, quando o consumo deveria ser zero. *(Resposta honesta: o ponto forte do sistema é a madrugada.)*

**6. Como vocês sabem que não vai dar alarme falso toda hora?**
Testamos com 14 dias simulados de consumo normal e o sistema não gerou nenhum alarme falso. *(Deixar claro que é teste com dados simulados; com dados reais, a calibração seria refinada.)*

**7. Os dados que vocês mostram são reais?**
Não, são simulados e estão marcados assim. O consumo normal segue estudos que mediram escolas públicas brasileiras (cerca de 10 L por aluno por dia).

### Sobre implantação e custo

**8. Precisa de obra? Precisa da autorização da Sanepar?**
Não há obra: a câmera só fotografa o hidrômetro que já existe, sem tocar no encanamento. Por usar o medidor da Sanepar, vale combinar a instalação com a companhia. *(Ser cauteloso: confirmar com a Sanepar antes de afirmar.)*

**9. Quanto custa?**
O modelo é por unidade monitorada, e o valor sai de um estudo de custos. A proposta é que a prefeitura pague com parte da **economia comprovada**: se não economizar, não paga. *(Não citar valores.)*

**10. Quem instala e quem cuida da manutenção?**
Na implantação, a equipe do projeto instala e calibra as câmeras; a manutenção (como troca de bateria) pode ser feita pela equipe de manutenção da prefeitura ou incluída no contrato.

**11. E se roubarem ou quebrarem a câmera?**
Ela fica dentro do abrigo do hidrômetro, numa caixa de proteção, e é de baixo custo. Se parar de enviar, o painel mostra "sem sinal" na hora. *(Detalhes de instalação ainda a definir.)*

**12. Como a câmera se conecta à internet?**
*(Questão em aberto — ver Parte 2. Combinar a resposta do grupo antes do pitch.)*

### Sobre gestão e impacto

**13. Por que não fecham a água automaticamente?**
Isso exigiria instalar uma válvula elétrica (obra) e poderia deixar uma escola sem água por um alarme errado. Preferimos que a decisão seja humana: o painel avisa e o gestor aciona a manutenção. A válvula fica como evolução futura.

**14. Como a manutenção fica sabendo do vazamento?**
O alerta aparece no painel do gestor, com a provável causa e o campo de operação (pendente → informado → consertado). Avisos no celular da manutenção ficam como evolução futura.

**15. Como vocês medem a economia?**
Antes de começar, o consumo médio de cada unidade vira a linha de base. A cada vazamento, a economia é a água que vazaria até a próxima conta menos a que realmente vazou até o conserto, convertida pela tarifa. Tudo fica num relatório mensal.

**16. A Sanepar já não faz isso?**
A Sanepar cuida da rede pública, antes do hidrômetro, e já investe em detecção de vazamentos na rede. O LeakFinder olha **depois** do hidrômetro, dentro dos prédios públicos, uma água que a prefeitura paga. Os trabalhos se completam.

**17. Por que começar pelas escolas?**
São muitas unidades, com horário bem definido (o que facilita a detecção), e falta d'água numa escola ou creche afeta diretamente alunos e famílias.

**18. Dá para usar na cidade inteira?**
Sim, em fases: escolas e CMEIs, depois todos os prédios municipais e, em parceria com a Sanepar, ajudar a localizar perdas na rede por bairro.

**19. E a privacidade (LGPD)?**
O sistema não coleta dados pessoais: só o consumo de água de prédios públicos. A câmera fotografa apenas o mostrador do hidrômetro.

**20. O que acontece com prédios que funcionam 24 horas, como UPAs?**
Eles não têm "horário fechado", então precisam de outra regra (a vazão mínima da madrugada). Está previsto como evolução futura.

**22. De onde vem o valor da economia? 15 dias não é exagero?**
É uma hipótese explícita e conservadora: sem o LeakFinder, um vazamento escondido (descarga, boia, torneira de madrugada)
só apareceria na conta mensal — usamos **metade** desse ciclo, 15 dias. A tarifa é a média de água da Sanepar em 2026
(R$ 7,00/m³), **sem esgoto** — então o valor real tende a ser maior. *(Atenção: um cano estourado costuma ser percebido
mais rápido, porque aparece água. Se a banca questionar, admitir que para vazamentos grandes a hipótese é generosa.)*

**23. E quando entra uma escola nova?**
O gestor cadastra pelo próprio painel (nome, tipo, horário e endereço, que vira um ponto no mapa). Ela aparece como
"aguardando câmera" e passa a ser monitorada assim que a ESP32-CAM é instalada. A média de consumo não é informada:
ela é medida pelo consumo semanal registrado.

**21. Existem soluções parecidas no mercado?**
*(Não pesquisamos concorrentes. Se a banca perguntar, citar o diferencial: sem obra, sem tomada, foco em prédios públicos e remuneração pela economia. Vale pesquisar antes do pitch.)*

---

## Dicas para a apresentação

- **Sempre diga "simulado"** ao mostrar números do protótipo.
- **Não prometa o que está em aberto** (conexão, custo, autorização da Sanepar): diga que é o próximo passo.
- **Para mostrar o alerta rápido na demonstração:** inicie o vazamento e aperte "+1 hora" uma ou duas vezes.
- **Frase de fechamento:** "Hoje um vazamento numa escola só aparece na conta do mês seguinte. Com o LeakFinder, em cerca de uma hora — sem obra, sem tomada e pago pela própria economia."
