################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../Drivers/PMS9003M/dfrobot_air_quality_sensor.c 

OBJS += \
./Drivers/PMS9003M/dfrobot_air_quality_sensor.o 

C_DEPS += \
./Drivers/PMS9003M/dfrobot_air_quality_sensor.d 


# Each subdirectory must supply rules for building sources it contributes
Drivers/PMS9003M/%.o Drivers/PMS9003M/%.su Drivers/PMS9003M/%.cyclo: ../Drivers/PMS9003M/%.c Drivers/PMS9003M/subdir.mk
	arm-none-eabi-gcc "$<" -mcpu=cortex-m33 -std=gnu11 -g3 -DDEBUG -DUSE_NUCLEO_64 -DUSE_HAL_DRIVER -DSTM32H533xx -c -I../Core/Inc -I../Drivers/STM32H5xx_HAL_Driver/Inc -I../Drivers/STM32H5xx_HAL_Driver/Inc/Legacy -I../Drivers/BSP/STM32H5xx_Nucleo -I../Drivers/CMSIS/Device/ST/STM32H5xx/Include -I../Drivers/CMSIS/Include -O0 -ffunction-sections -fdata-sections -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv5-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Drivers-2f-PMS9003M

clean-Drivers-2f-PMS9003M:
	-$(RM) ./Drivers/PMS9003M/dfrobot_air_quality_sensor.cyclo ./Drivers/PMS9003M/dfrobot_air_quality_sensor.d ./Drivers/PMS9003M/dfrobot_air_quality_sensor.o ./Drivers/PMS9003M/dfrobot_air_quality_sensor.su

.PHONY: clean-Drivers-2f-PMS9003M

