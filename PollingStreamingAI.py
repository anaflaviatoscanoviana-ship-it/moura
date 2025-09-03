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

import numpy as np
from scipy.integrate import cumulative_trapezoid


# ... (O resto do seu código inicial, como a função saveFile, permanece o mesmo) ...
# Configure os parâmetros a seguir
deviceDescription = "USB-4716,BID#1"
profilePath = u"C:/Advantech/DAQNavi/Examples/profile/USB-4716.xml"

startChannel = 0
channelCount = 1

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
                if valores[0] > 0.001: # Condição ajustada para canal único
                #if True: # Descomente esta linha para salvar todos os dados, ignorando a condição
                
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

    # --- ALTERAÇÃO 1: Preparar listas para armazenar TODOS os dados para o gráfico ---
    # Usamos listas normais em vez de 'deque' com 'maxlen'
    eixo_x_ms = []
    eixo_y_ch0 = []

    # A configuração e exibição do gráfico foram movidas para depois do loop de coleta.

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
        print("Coleta de dados em progresso... Pressione qualquer tecla para parar.")

        # --- LÓGICA DE TIMESTAMP MELHORADA ---
        hora_inicio_coleta = datetime.datetime.now()
        taxa_por_canal = wfAiCtrl.conversion.clockRate / channelCount
        intervalo_por_amostra = datetime.timedelta(seconds=1.0 / taxa_por_canal)
        contador_amostras_processadas = 0

        while not kbhit():
            result = wfAiCtrl.getData(USER_BUFFER_SIZE, -1)
            ret, returnedCount, data, = result[0], result[1], result[2]

            if BioFailed(ret):
                break
                
            if returnedCount > 0 and statistics.mean(data) > 0.01:
                for i in range(0, returnedCount, channelCount):
                    amostras_da_leitura = data[i : i + channelCount]
                    if (len(amostras_da_leitura) == channelCount):
                        indice_no_bloco = i // channelCount
                        deslocamento_total = (contador_amostras_processadas + indice_no_bloco) * intervalo_por_amostra
                        timestamp_exato = hora_inicio_coleta + deslocamento_total
                        
                        # Armazena todos os dados para o arquivo CSV
                        dados_coletados.append((timestamp_exato, amostras_da_leitura))
                        
                        # --- ALTERAÇÃO 2: Apenas coleta os dados para o gráfico, sem desenhar ---
                        delta_tempo = timestamp_exato - hora_inicio_coleta
                        tempo_decorrido_ms = delta_tempo.total_seconds() * 1000
                        
                        eixo_x_ms.append(tempo_decorrido_ms)
                        eixo_y_ch0.append(amostras_da_leitura[0])
                
                contador_amostras_processadas += (returnedCount // channelCount)
        
        print("\nColeta interrompida pelo usuário.")
        # Passo 6: Parar a operação
        ret = wfAiCtrl.stop()

    # Passo 7: Liberar recursos
    wfAiCtrl.release()
    wfAiCtrl.dispose()

    print("Gerando gráfico final...")

    #  CALCULAR A INTEGRAL 
    if len(eixo_x_ms) > 1: # Precisa de pelo menos 2 pontos para integrar
        tempo_segundos = np.array(eixo_x_ms) / 1000.0
        tensao_volts = np.array(eixo_y_ch0)
        sinal_integrado = cumulative_trapezoid(tensao_volts, tempo_segundos, initial=0)
    else:
        sinal_integrado = [] # Não há dados suficientes para integrar

    # ACRESCENTAR O BLOCO DE PLOTAGEM QUE VOCÊ ENVIOU
    # Configura a figura e o eixo principal (para o sinal original)
    fig, ax1 = plt.subplots()

    # Plot do sinal original (eixo Y à esquerda)
    cor_original = 'r'
    ax1.set_xlabel("Tempo Decorrido (ms)")
    ax1.set_ylabel("Valor Lido (V)", color=cor_original)
    ax1.plot(eixo_x_ms, eixo_y_ch0, color=cor_original, label='Sinal Original (V)')
    ax1.tick_params(axis='y', labelcolor=cor_original)
    ax1.grid(True)

    # Cria um segundo eixo Y que compartilha o mesmo eixo X
    ax2 = ax1.twinx()
    cor_integrado = 'b'
    ax2.set_ylabel('Sinal Integrado (V·s)', color=cor_integrado)
    # Plot do sinal integrado (eixo Y à direita)
    ax2.plot(eixo_x_ms, sinal_integrado, color=cor_integrado, linestyle='--', label='Sinal Integrado (V·s)')
    ax2.tick_params(axis='y', labelcolor=cor_integrado)

    # Título e legenda
    ax1.set_title("Sinal Original vs. Sinal Integrado")
    fig.tight_layout() # Ajusta o layout para não cortar os labels
    
    # Combina as legendas dos dois eixos
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='best')

    # Salva o gráfico em um arquivo de imagem
    nome_arquivo_grafico = datetime.datetime.now().strftime("grafico_%Y-%m-%d_%H-%M-%S.png")
    fig.savefig(nome_arquivo_grafico, bbox_inches='tight')
    print(f"Gráfico final salvo como '{nome_arquivo_grafico}'")

    # Salva os dados brutos no arquivo CSV
    saveFile(dados_coletados)

    # Exibe o gráfico na tela
    print("Exibindo gráfico. Feche a janela para finalizar o programa.")
    plt.show()

    if BioFailed(ret):
        enumStr = AdxEnumToString("ErrorCode", ret.value, 256)
        print("Some error occurred. And the last error code is %#x. [%s]" %
              (ret.value, enumStr))
        
    return 0

if __name__ == '__main__':
    AdvPollingStreamingAI()