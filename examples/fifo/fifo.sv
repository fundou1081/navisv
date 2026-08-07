// fifo.sv — Synchronous FIFO with read/write pointers
// 64-deep, 8-bit wide, with full/empty/almost_full/almost_empty flags
module fifo #(
    parameter DEPTH = 64,
    parameter WIDTH = 8
) (
    input  logic             clk, rst_n,
    input  logic             wr_en, rd_en,
    input  logic [WIDTH-1:0] wr_data,
    output logic [WIDTH-1:0] rd_data,
    output logic             full, empty,
    output logic             almost_full, almost_empty
);
    logic [WIDTH-1:0] mem [0:DEPTH-1];
    logic [$clog2(DEPTH):0] wr_ptr, rd_ptr;  // one extra bit for full/empty

    wire logic [$clog2(DEPTH):0] wr_ptr_next = wr_ptr + 1'b1;
    wire logic [$clog2(DEPTH):0] rd_ptr_next = rd_ptr + 1'b1;
    wire logic                     write      = wr_en && !full;
    wire logic                     read       = rd_en && !empty;

    // Full when pointers differ only in MSB, same otherwise
    assign full         = (wr_ptr[$clog2(DEPTH)] != rd_ptr[$clog2(DEPTH)]) &&
                          (wr_ptr[$clog2(DEPTH)-1:0] == rd_ptr[$clog2(DEPTH)-1:0]);
    assign empty        = (wr_ptr == rd_ptr);
    assign almost_full  = (wr_ptr_next[$clog2(DEPTH)] != rd_ptr[$clog2(DEPTH)]) &&
                          (wr_ptr_next[$clog2(DEPTH)-1:0] == rd_ptr[$clog2(DEPTH)-1:0]);
    assign almost_empty = (wr_ptr == rd_ptr_next);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
        end else begin
            if (write) begin
                mem[wr_ptr[$clog2(DEPTH)-1:0]] <= wr_data;
                wr_ptr <= wr_ptr_next;
            end
            if (read) begin
                rd_data <= mem[rd_ptr[$clog2(DEPTH)-1:0]];
                rd_ptr <= rd_ptr_next;
            end
        end
    end
endmodule
