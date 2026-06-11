/*!
 * @file  pms9003m.h
 * @brief DMA-based driver for the Plantower PMS9003M particulate-matter sensor
 *        over its native UART (9600 8N1, active mode).
 *
 * The sensor streams a fixed 32-byte frame roughly once per second. Reception
 * is fully interrupt/DMA driven: the UART idle line delimits each frame and the
 * RX event callback validates and decodes it, so the application only has to
 * poll @ref PMS9003M_HasNewData.
 */

#ifndef PMS9003M_H
#define PMS9003M_H

#include "stm32h5xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

/* Landing buffer for one frame plus margin (frame is 32 bytes). */
#define PMS9003M_RX_BUF_SIZE 64

/** Decoded contents of one PMS9003M data frame. */
typedef struct
{
  /* PM concentration, standard particle (CF=1), micrograms / m^3 */
  uint16_t pm1_0_std;
  uint16_t pm2_5_std;
  uint16_t pm10_std;

  /* PM concentration, atmospheric environment, micrograms / m^3 */
  uint16_t pm1_0_atm;
  uint16_t pm2_5_atm;
  uint16_t pm10_atm;

  /* Particle counts, particles per 0.1 L of air */
  uint16_t n0_3;
  uint16_t n0_5;
  uint16_t n1_0;
  uint16_t n2_5;
  uint16_t n5_0;
  uint16_t n10;

  uint8_t version;
  uint8_t error_code;
} PMS9003M_Data_t;

/** Driver instance. Allocate one and pass it to every call. */
typedef struct
{
  UART_HandleTypeDef huart;
  DMA_HandleTypeDef  hdma_rx;
  uint8_t            rx_buf[PMS9003M_RX_BUF_SIZE];

  PMS9003M_Data_t    data;          /* last checksum-valid frame */
  volatile uint32_t  frame_count;   /* total valid frames received */
  volatile bool      new_frame;     /* set on new frame, cleared by HasNewData */
} PMS9003M_t;

/**
 * @brief Bring up USART1 + GPDMA on PA9(TX)/PA10(RX) and start reception.
 * @note  Only RX (PA10) is required; wire the sensor TX to PA10.
 * @return true on success.
 */
bool PMS9003M_Init(PMS9003M_t *dev);

/**
 * @brief Test-and-clear: returns true once for each newly received valid frame.
 */
bool PMS9003M_HasNewData(PMS9003M_t *dev);

/**
 * @brief Access the most recently decoded frame.
 */
const PMS9003M_Data_t *PMS9003M_GetData(PMS9003M_t *dev);

/* Interrupt trampolines — call these from the matching handlers in
 * stm32h5xx_it.c (USART1_IRQHandler and GPDMA1_Channel0_IRQHandler). */
void PMS9003M_USART1_IRQHandler(void);
void PMS9003M_GPDMA1_Channel0_IRQHandler(void);

#endif /* PMS9003M_H */
