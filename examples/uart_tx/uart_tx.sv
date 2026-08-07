// uart_tx.sv — UART Transmitter (8N1, configurable baud rate)
// 经典串行通信模块
module uart_tx #(
    parameter CLK_FREQ = 50_000_000,  // 50 MHz
    parameter BAUD     = 115200       // 115.2 kbps
) (
    input  logic         clk, rst_n,
    input  logic         send,           // pulse to start transmission
    input  logic [7:0]   tx_data,        // byte to send
    output logic         tx,             // serial output line
    output logic         busy,           // 1 = transmitting
    output logic         done            // 1 cycle pulse when done
);
    localparam DIV = CLK_FREQ / BAUD;

    logic [$clog2(DIV)-1:0] baud_cnt;
    logic [3:0]             bit_cnt;   // 0=start, 1-8=data, 9=stop
    logic [8:0]             shift_reg; // {stop, data[7:0], start}

    typedef enum logic [1:0] {
        IDLE, START, DATA, STOP
    } state_t;
    state_t state, next_state;

    always_comb begin
        next_state = state;
        case (state)
            IDLE:  if (send)                     next_state = START;
            START: if (baud_cnt == DIV - 1)      next_state = DATA;
            DATA:  if (baud_cnt == DIV - 1 &&
                         bit_cnt == 4'd9)        next_state = STOP;
            STOP:  if (baud_cnt == DIV - 1)      next_state = IDLE;
        endcase
    end

    assign busy  = (state != IDLE);
    assign done  = (state == STOP) && (baud_cnt == DIV - 1);
    assign tx    = shift_reg[0];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= IDLE;
            baud_cnt <= '0;
            bit_cnt  <= '0;
            shift_reg <= 9'b1_1111_1111;  // idle high
        end else begin
            state <= next_state;

            case (state)
                IDLE: begin
                    baud_cnt <= '0;
                    bit_cnt  <= '0;
                    if (send)
                        shift_reg <= {1'b1, tx_data, 1'b0};  // stop + data + start
                end
                START, DATA, STOP: begin
                    if (baud_cnt == DIV - 1) begin
                        baud_cnt   <= '0;
                        shift_reg <= shift_reg >> 1;
                        if (state == START)
                            bit_cnt <= 4'd1;
                        else if (state == DATA)
                            bit_cnt <= bit_cnt + 4'd1;
                    end else begin
                        baud_cnt <= baud_cnt + 1'b1;
                    end
                end
            endcase
        end
    end
endmodule
