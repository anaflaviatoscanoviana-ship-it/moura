#!/usr/bin/python
# -*- coding:utf-8 -*-

import datetime
import sys, os
import time
import statistics
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             os.path.pardir)))
from CommonUtils import kbhit

from Automation.BDaq import *
from Automation.BDaq.WaveformAiCtrl import WaveformAiCtrl
from Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed

import matplotlib.pyplot as plt
from collections import deque
from matplotlib.ticker import FuncFormatter


# Configure os parâmetros a seguir
deviceDescription = "DemoDevice,BID#0"
profilePath = u"C:/Advantech/DAQNavi/Examples/profile/USB-4716.xml"

startChannel = 0
channelCount = 2

sectionLength = 100
sectionCount = 0 # 0 = Modo Streaming (contínuo)

userParam = DaqEventParam()

@DaqEventCallback(None, c_void_p, POINTER(BfdAiEventArgs), c_void_p)
def OnBurnoutEvent(sender, args, userParam):
    status  = cast(args, POINTER(BfdAiEventArgs))[0]
    channel = status.Offset
    print("AI Channel%d is burntout!" % (channel))

USER_BUFFER_SIZE = channelCount * sectionLength

def saveFile(dados_coletados):
    # --- Bloco de Salvamento ---
    if len(dados_coletados) > 0:
        print(f"\nColeta finalizada. Salvando dados em arquivo...")

        agora = datetime.datetime.now()
        nome_do_arquivo = agora.strftime("dados_%Y-%m-%d_%H-%M-%S.csv")

        with open(nome_do_arquivo, "w") as f:
            # Escreve o cabeçalho das colunas
            cabecalho = "Timestamp, " + ", ".join([f"Canal_{i}" for i in range(startChannel, startChannel + channelCount)])
            f.write(cabecalho + "\n")

            # Percorre a lista de dados coletados e escreve no arquivo
            for amostra_completa in dados_coletados:
                timestamp, valores = amostra_completa

                # Verifica se os valores de ambos os canais atendem à condição
                #if valores[0] > 0.001 and valores[1] > 0.001:
                if True: # Descomente esta linha para salvar todos os dados, ignorando a condição
                
                    # O bloco abaixo só executa se a condição 'if' for verdadeira.
                    
                    # Formata o timestamp para incluir milissegundos
                    timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    # Formata os valores numéricos
                    valores_str = ", ".join([f"{valor:.6f}" for valor in valores])
                    # Cria a linha de texto completa
                    linha = f"{timestamp_str}, {valores_str}"
                    # Escreve a linha no arquivo
                    f.write(linha + "\n")
                    
            print(f"Arquivo '{nome_do_arquivo}' salvo com sucesso!")

def AdvPollingStreamingAI():
    ret = ErrorCode.Success

    # Passo 1: Criar o controlador WaveformAiCtrl
    wfAiCtrl = WaveformAiCtrl(deviceDescription)
    wfAiCtrl.addBurnOutHandler(OnBurnoutEvent, userParam)

    dados_coletados = []

    # Preparar os dados para o gráfico em tempo real
    # Usamos deque com 'maxlen' para manter apenas as últimas 500 amostras na tela,
    # evitando que o gráfico fique lento com o tempo.
    max_plot_points = 500
    eixo_x_ms = deque(maxlen=max_plot_points)
    eixo_y_ch0 = deque(maxlen=max_plot_points)
    eixo_y_ch1 = deque(maxlen=max_plot_points)

    # NOVO: Configurar o gráfico
    plt.ion() # Habilita o modo interativo
    fig, ax = plt.subplots() # Cria a figura e os eixos do gráfico
    ax.set_xlabel("Tempo Decorrido (ms)")
    ax.set_xlabel("Horário da Coleta")
    ax.set_ylabel("Valor Lido (V)")
    ax.grid(True)

    def format_ms(x, pos):
        return f'{int(x)} ms'
    ax.xaxis.set_major_formatter(FuncFormatter(format_ms))

    # O plot inicial agora usa a nova variável
    line0, = ax.plot(eixo_x_ms, eixo_y_ch0, 'r-', label=f'Canal {startChannel}')    # Linha vermelha
    line1, = ax.plot(eixo_x_ms, eixo_y_ch1, 'b-', label=f'Canal {startChannel + 1}') # Linha azul

    ax.legend()

    for _ in range(1):
        # Carrega o perfil para inicializar o dispositivo
        wfAiCtrl.loadProfile = profilePath
        
        # Passo 2: Configurar os parâmetros da operação
        wfAiCtrl.conversion.channelStart = startChannel
        wfAiCtrl.conversion.channelCount = channelCount
        wfAiCtrl.conversion.clockRate    = 1000 # Taxa de amostragem TOTAL

        wfAiCtrl.record.sectionCount = sectionCount  
        wfAiCtrl.record.sectionLength = sectionLength

        # Passo 3: Preparar e iniciar a operação
        ret = wfAiCtrl.prepare()
        if BioFailed(ret):
            break

        ret = wfAiCtrl.start()
        if BioFailed(ret):
            break

        # Passo 4: Coletar dados em tempo real
        print("Coleta de dados em progresso... Pressione qualquer tecla para parar e salvar.")

        # --- LÓGICA DE TIMESTAMP MELHORADA ---
        # 1. Marca o tempo de início exato da aquisição
        hora_inicio_coleta = datetime.datetime.now()
        
        # 2. Calcula a taxa de amostragem para cada canal individualmente
        #    Se a taxa total é 2000 Hz para 2 canais, então cada canal tem 1000 amostras/segundo.
        taxa_por_canal = wfAiCtrl.conversion.clockRate / channelCount
        intervalo_por_amostra = datetime.timedelta(seconds=1.0 / taxa_por_canal)
        
        # 3. Mantém um contador de quantas amostras (por canal) já foram processadas
        contador_amostras_processadas = 0
        # --- FIM DA MELHORIA ---

        while not kbhit():
            #time.sleep( 1 / 10)
            result = wfAiCtrl.getData(USER_BUFFER_SIZE, -1)
            ret, returnedCount, data, = result[0], result[1], result[2]
            #print(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
            #print("Read: ",returnedCount)
            #print("data: ",data)
            if BioFailed(ret):
                break
            #if returnedCount > 0 and statistics.mean(data) > 0.01:
            if returnedCount > 0:
                count = 0
                for i in range(0, returnedCount, channelCount):
                    count = count + 1
                    amostras_da_leitura = data[i : i + channelCount]
                if (len(amostras_da_leitura) == channelCount):
                        # --- CÁLCULO PRECISO DO TIMESTAMP ---
                        # Pega o índice da amostra dentro do bloco atual (0, 1, 2, ...)
                        indice_no_bloco = i // channelCount
                        
                        # Calculs
                        # a o deslocamento de tempo desde o início da coleta
                        deslocamento_total = (contador_amostras_processadas + indice_no_bloco) * intervalo_por_amostra
                        timestamp_exato = hora_inicio_coleta + deslocamento_total
                        # --- FIM DO CÁLCULO ---
                        
                        dados_coletados.append((timestamp_exato, amostras_da_leitura))
                        
                        # 1. Calcula a diferença de tempo desde o início
                        delta_tempo = timestamp_exato - hora_inicio_coleta
                        # 2. Converte essa diferença para milissegundos
                        tempo_decorrido_ms = delta_tempo.total_seconds() * 1000
                        
                        # 3. Adiciona o valor em milissegundos ao eixo X do gráfico
                        eixo_x_ms.append(tempo_decorrido_ms)

                        eixo_y_ch0.append(amostras_da_leitura[0]) # Primeiro valor vai para o Canal 0
                        eixo_y_ch1.append(amostras_da_leitura[1]) # Segundo valor vai para o Canal 1

                line0.set_data(eixo_x_ms, eixo_y_ch0)
                line1.set_data(eixo_x_ms, eixo_y_ch1)
                
                ax.relim()
                ax.autoscale_view()
                plt.setp(ax.get_xticklabels(), rotation=30, ha='right')
                fig.canvas.draw()
                fig.canvas.flush_events()
                
                contador_amostras_processadas += (returnedCount // channelCount)
            
        # Passo 6: Parar a operação
        ret = wfAiCtrl.stop()

    # Passo 7: Liberar recursos
    wfAiCtrl.release()
    wfAiCtrl.dispose()

    nome_arquivo_grafico = datetime.datetime.now().strftime("grafico_%Y-%m-%d_%H-%M-%S.png")
    fig.savefig(nome_arquivo_grafico)

    fig.savefig(nome_arquivo_grafico, bbox_inches='tight')
    print(f"Gráfico final salvo como '{nome_arquivo_grafico}'")
    saveFile(dados_coletados)

    #  Desliga o modo interativo e mostra o gráfico final
    plt.ioff()
    plt.show()


    if BioFailed(ret):
        enumStr = AdxEnumToString("ErrorCode", ret.value, 256)
        print("Some error occurred. And the last error code is %#x. [%s]" %
              (ret.value, enumStr))
        
    return 0

if __name__ == '__main__':
    AdvPollingStreamingAI()