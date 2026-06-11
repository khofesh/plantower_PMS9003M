/*!
 * @file  pms9003m.c
 * @brief DMA-based PMS9003M UART driver implementation.
 *
 * Frame layout (32 bytes, big-endian):
 *   [0..1]   header 0x42 0x4D
 *   [2..3]   frame length (0x001C = 28)
 *   [4..9]   PM1.0 / PM2.5 / PM10  (standard particle, CF=1)
 *   [10..15] PM1.0 / PM2.5 / PM10  (atmospheric environment)
 *   [16..27] counts >0.3/0.5/1.0/2.5/5.0/10 um per 0.1 L
 *   [28]     version   [29] error code
 *   [30..31] checksum = sum of bytes [0..29]
 */

#include "pms9003m.h"

#define PMS_FRAME_LEN   32U
#define PMS_HEADER_0    0x42U
#define PMS_HEADER_1    0x4DU
#define PMS_FRAME_BODY  28U   /* value of the length field */

/* Single instance, registered at init, used by the IRQ trampolines. */
static PMS9003M_t *s_dev = NULL;

static inline uint16_t be16(const uint8_t *p)
{
  return (uint16_t)(((uint16_t)p[0] << 8) | (uint16_t)p[1]);
}

/**
 * @brief Locate and validate a frame inside @p buf, decoding into @p out.
 * @return true if a checksum-valid frame was found.
 */
static bool pms_parse(const uint8_t *buf, uint16_t size, PMS9003M_Data_t *out)
{
  if (size < PMS_FRAME_LEN)
  {
    return false;
  }

  /* scan for the header so we tolerate leading garbage / misalignment */
  for (uint16_t s = 0; s + PMS_FRAME_LEN <= size; s++)
  {
    if (buf[s] != PMS_HEADER_0 || buf[s + 1] != PMS_HEADER_1)
    {
      continue;
    }

    const uint8_t *f = &buf[s];

    if (be16(&f[2]) != PMS_FRAME_BODY)
    {
      continue;
    }

    uint16_t sum = 0;
    for (uint8_t i = 0; i < PMS_FRAME_LEN - 2; i++)
    {
      sum += f[i];
    }
    if (sum != be16(&f[30]))
    {
      continue;
    }

    out->pm1_0_std  = be16(&f[4]);
    out->pm2_5_std  = be16(&f[6]);
    out->pm10_std   = be16(&f[8]);
    out->pm1_0_atm  = be16(&f[10]);
    out->pm2_5_atm  = be16(&f[12]);
    out->pm10_atm   = be16(&f[14]);
    out->n0_3       = be16(&f[16]);
    out->n0_5       = be16(&f[18]);
    out->n1_0       = be16(&f[20]);
    out->n2_5       = be16(&f[22]);
    out->n5_0       = be16(&f[24]);
    out->n10        = be16(&f[26]);
    out->version    = f[28];
    out->error_code = f[29];
    return true;
  }

  return false;
}

/* Re-arm idle-terminated DMA reception from the start of the buffer.
 * The half-transfer interrupt is disabled so only a full buffer or an idle
 * line produces an RX event, keeping each event aligned to a frame burst. */
static void pms_start_rx(PMS9003M_t *dev)
{
  if (HAL_UARTEx_ReceiveToIdle_DMA(&dev->huart, dev->rx_buf, PMS9003M_RX_BUF_SIZE) == HAL_OK)
  {
    __HAL_DMA_DISABLE_IT(&dev->hdma_rx, DMA_IT_HT);
  }
}

bool PMS9003M_Init(PMS9003M_t *dev)
{
  if (dev == NULL)
  {
    return false;
  }

  s_dev = dev;
  dev->frame_count = 0;
  dev->new_frame   = false;

  GPIO_InitTypeDef gpio = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_USART1_CLK_ENABLE();
  __HAL_RCC_GPDMA1_CLK_ENABLE();

  /* PA9 = USART1_TX, PA10 = USART1_RX (AF7); only RX is needed for the PMS */
  gpio.Pin       = GPIO_PIN_9 | GPIO_PIN_10;
  gpio.Mode      = GPIO_MODE_AF_PP;
  gpio.Pull      = GPIO_NOPULL;
  gpio.Speed     = GPIO_SPEED_FREQ_LOW;
  gpio.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(GPIOA, &gpio);

  /* GPDMA1 channel 0: USART1_RX -> memory, byte width, destination incrementing */
  dev->hdma_rx.Instance                 = GPDMA1_Channel0;
  dev->hdma_rx.Init.Request             = GPDMA1_REQUEST_USART1_RX;
  dev->hdma_rx.Init.BlkHWRequest        = DMA_BREQ_SINGLE_BURST;
  dev->hdma_rx.Init.Direction           = DMA_PERIPH_TO_MEMORY;
  dev->hdma_rx.Init.SrcInc              = DMA_SINC_FIXED;
  dev->hdma_rx.Init.DestInc             = DMA_DINC_INCREMENTED;
  dev->hdma_rx.Init.SrcDataWidth        = DMA_SRC_DATAWIDTH_BYTE;
  dev->hdma_rx.Init.DestDataWidth       = DMA_DEST_DATAWIDTH_BYTE;
  dev->hdma_rx.Init.Priority            = DMA_LOW_PRIORITY_LOW_WEIGHT;
  dev->hdma_rx.Init.SrcBurstLength      = 1;
  dev->hdma_rx.Init.DestBurstLength     = 1;
  dev->hdma_rx.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT0 | DMA_DEST_ALLOCATED_PORT0;
  dev->hdma_rx.Init.TransferEventMode   = DMA_TCEM_BLOCK_TRANSFER;
  dev->hdma_rx.Init.Mode                = DMA_NORMAL;
  if (HAL_DMA_Init(&dev->hdma_rx) != HAL_OK)
  {
    return false;
  }
  __HAL_LINKDMA(&dev->huart, hdmarx, dev->hdma_rx);

  /* USART1 @ 9600 8N1 */
  dev->huart.Instance          = USART1;
  dev->huart.Init.BaudRate     = 9600;
  dev->huart.Init.WordLength   = UART_WORDLENGTH_8B;
  dev->huart.Init.StopBits     = UART_STOPBITS_1;
  dev->huart.Init.Parity       = UART_PARITY_NONE;
  dev->huart.Init.Mode         = UART_MODE_TX_RX;
  dev->huart.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
  dev->huart.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&dev->huart) != HAL_OK)
  {
    return false;
  }

  /* DMA channel interrupt must be higher priority (lower number) is not
   * required, but both must be enabled for ReceiveToIdle_DMA to work. */
  HAL_NVIC_SetPriority(GPDMA1_Channel0_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel0_IRQn);
  HAL_NVIC_SetPriority(USART1_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(USART1_IRQn);

  pms_start_rx(dev);
  return true;
}

bool PMS9003M_HasNewData(PMS9003M_t *dev)
{
  if (dev == NULL || !dev->new_frame)
  {
    return false;
  }
  dev->new_frame = false;
  return true;
}

const PMS9003M_Data_t *PMS9003M_GetData(PMS9003M_t *dev)
{
  return (dev != NULL) ? &dev->data : NULL;
}

/* Called by HAL on idle line / buffer full. Size = bytes received this burst. */
void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
  if (s_dev == NULL || huart->Instance != USART1)
  {
    return;
  }

  if (pms_parse(s_dev->rx_buf, Size, &s_dev->data))
  {
    s_dev->frame_count++;
    s_dev->new_frame = true;
  }

  pms_start_rx(s_dev);
}

void PMS9003M_USART1_IRQHandler(void)
{
  if (s_dev != NULL)
  {
    HAL_UART_IRQHandler(&s_dev->huart);
  }
}

void PMS9003M_GPDMA1_Channel0_IRQHandler(void)
{
  if (s_dev != NULL)
  {
    HAL_DMA_IRQHandler(&s_dev->hdma_rx);
  }
}
